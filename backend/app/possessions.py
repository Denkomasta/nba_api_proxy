"""Turns a game's play-by-play into an event log with one case per possession.

`assign_possessions` splits the events: a possession ends with a made basket, a last free throw, a
turnover, a defensive rebound, a jump ball won by the other team or the end of a period. It is worked out from the events because only
the live feed has a `possession` field, and that field holds a team, not a possession number.

`event_log` then shapes each possession as a trace that starts with how the team got the ball and
ends with how it was finished. Activities are named from the side of the team with the ball.
"""

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

SHOTS = {"2pt", "3pt", "heave", "Made Shot", "Missed Shot"}
FREE_THROWS = {"freethrow", "Free Throw"}
TURNOVERS = {"turnover", "Turnover"}
REBOUNDS = {"rebound", "Rebound"}
FOULS = {"foul", "Foul"}
JUMP_BALLS = {"jumpball", "Jump Ball"}
VIOLATIONS = {"violation", "Violation"}

# After these fouls the fouled team shoots and then keeps the ball
BALL_KEPT = ("flagrant", "clear-path", "clear path", "away-from-play", "away from play", "transition take")

# Lower-cased action types left out of the event log
DROPPED = {"substitution", "game", "ejection", "instantreplay", "instant replay", "stoppage", "memo", ""}

OPPONENT_REBOUND = "Opponent Defensive Rebound"
OPPONENT_JUMP_BALL = "Opponent Jump Ball"
GOALTENDING = "Goaltending"
# A possession that stops on one of these is finished, so it needs no Period End
FINISHED = {"Made 2PT", "Made 3PT", "Made Free Throw", "Turnover", OPPONENT_REBOUND, OPPONENT_JUMP_BALL, GOALTENDING}
SCORES = {"Made 2PT", "Made 3PT", "Made Free Throw"}

_FREE_THROW_NUMBER = re.compile(r"(\d) of (\d)")


@dataclass
class _Possession:
    team: str | None
    events: list[int] = field(default_factory=list)
    # Something happened that only the team with the ball does, not just subs or a jump ball
    acted: bool = False


@dataclass
class LogEntry:
    possession: int
    team: str | None
    activity: str
    # Position in the game's events. A derived entry points at the event it was derived from.
    index: int
    # Not an event of its own in the feed: an inbound, or the second copy of a rebound or jump ball
    derived: bool = False


def _team_lookup(events: list[dict[str, Any]]) -> Callable[[dict[str, Any]], str | None]:
    # The stats feed leaves the team out of team rebounds and team turnovers, but not the location
    by_location = {e["location"]: e["teamTricode"] for e in events if e.get("location") and e.get("teamTricode")}

    def team_of(event: dict[str, Any]) -> str | None:
        return event.get("teamTricode") or by_location.get(event.get("location"))

    return team_of


def _clock_key(event: dict[str, Any]) -> tuple[Any, Any]:
    return event.get("period"), event.get("clock")


def _technical_free_throws(events: list[dict[str, Any]]) -> set[int]:
    """Indexes of free throws that leave the possession alone.

    The stats feed names them. The live feed calls them "1 of 1", so they are matched with a
    technical foul at the same clock.
    """
    technicals: Counter[tuple[Any, Any]] = Counter()
    for event in events:
        if event.get("actionType") in FOULS:
            foul = f"{event.get('subType')} {event.get('descriptor')}".lower()
            technicals[_clock_key(event)] += "technical" in foul and "double" not in foul

    found = set()
    for index, event in enumerate(events):
        if event.get("actionType") not in FREE_THROWS:
            continue
        sub_type = str(event.get("subType"))
        if "Technical" in sub_type:
            found.add(index)
        elif sub_type == "1 of 1" and technicals[_clock_key(event)] > 0:
            technicals[_clock_key(event)] -= 1
            found.add(index)
    return found


def _action_type(event: dict[str, Any]) -> str:
    """The event's action type. The stats feed leaves it empty on steals and blocks."""
    action = str(event.get("actionType") or "")
    if action:
        return action
    description = str(event.get("description"))
    return "steal" if "STEAL" in description else "block" if "BLOCK" in description else ""


def _is_period_start(event: dict[str, Any]) -> bool:
    return str(event.get("actionType")).lower() == "period" and "start" in f"{event.get('subType')} {event.get('description')}".lower()


def period_starts_first(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The events with each Period Start in front of anything the feed logs before it in that period."""
    ordered: list[dict[str, Any]] = []
    period = None
    first = 0
    for event in events:
        if event.get("period") != period:
            period = event.get("period")
            first = len(ordered)
        ordered.insert(first if _is_period_start(event) else len(ordered), event)
    return ordered


def _jump_ball_winner(events: list[dict[str, Any]], team_of: Callable[[dict[str, Any]], str | None]) -> Callable[[dict[str, Any]], str | None]:
    """Finds the team that won a jump ball, or None if it can't be told.

    The live feed puts that team on the event. The stats feed puts the first jumper's team there, so
    the winner comes from "Tip to <last name>", matched with the names on the game's other events.
    """
    players: dict[str, set[str]] = {}
    for event in events:
        team = team_of(event)
        if event.get("playerName") and team and event.get("actionType") not in JUMP_BALLS:
            players.setdefault(event["playerName"], set()).add(team)

    def winner(event: dict[str, Any]) -> str | None:
        if event.get("jumpBallRecoveredName"):
            return team_of(event)
        _, tip, name = str(event.get("description")).partition("Tip to ")
        teams = players.get(name.strip(), set()) if tip else set()
        return next(iter(teams)) if len(teams) == 1 else None

    return winner


def _next_play(events: list[dict[str, Any]], index: int) -> dict[str, Any] | None:
    """The next event after `index` that isn't a stoppage."""
    ignored = DROPPED | {"timeout", "steal", "block"}
    return next((e for e in events[index + 1 :] if _action_type(e).lower() not in ignored), None)


def assign_possessions(events: list[dict[str, Any]]) -> list[tuple[int, str | None]]:
    """(possession number from 1, team with the ball) for each event, in the order of `events`.

    Substitutions, timeouts and other dead-ball events go with the possession that follows them,
    or with the one before them at the end of a period.
    """
    team_of = _team_lookup(events)
    jump_ball_winner = _jump_ball_winner(events, team_of)
    teams = list(dict.fromkeys(filter(None, map(team_of, events))))

    def opponent(team: str) -> str | None:
        return next((t for t in teams if t != team), None)

    technical = _technical_free_throws(events)
    # A made basket with free throws after it at the same clock is an and-one, which they finish
    last_free_throw = {
        (*_clock_key(e), team_of(e)): i
        for i, e in enumerate(events)
        if e.get("actionType") in FREE_THROWS and i not in technical
    }
    fouls: dict[tuple[Any, Any], list[tuple[str | None, str]]] = {}
    for event in events:
        if event.get("actionType") in FOULS:
            foul = f"{event.get('subType')} {event.get('descriptor')}".lower()
            fouls.setdefault(_clock_key(event), []).append((team_of(event), foul))

    finished: list[_Possession] = []
    current = _Possession(None)
    period = None
    # A miss is in the air: the next rebound decides who has the ball
    rebound_open = False
    # Clock and team of the basket that closed the last possession
    basket = None

    def close(next_team: str | None) -> None:
        nonlocal current, rebound_open
        finished.append(current)
        current = _Possession(next_team)
        rebound_open = False

    def end_period() -> None:
        nonlocal current, rebound_open
        if current.acted:
            close(None)
        elif finished:
            finished[-1].events += current.events
            current = _Possession(None)
        rebound_open = False

    def lost_on_turnover(index: int) -> bool:
        # A held ball is often logged as jump ball, turnover, steal. The turnover then ends the possession.
        play = _next_play(events, index)
        return bool(play) and play.get("actionType") in TURNOVERS and team_of(play) == current.team

    for index, event in enumerate(events):
        if event.get("period") != period:
            end_period()
            period = event.get("period")

        action = event.get("actionType")
        team = team_of(event)
        is_free_throw = action in FREE_THROWS and index not in technical

        # Logged after the basket it gave, which has already closed the possession
        if action in VIOLATIONS and "goaltending" in str(event.get("subType")).lower() and team and basket == (*_clock_key(event), opponent(team)):
            finished[-1].events.append(index)
            continue

        # Whoever does this has the ball, even if the feed skipped how they got it
        if team and team != current.team and (action in SHOTS or action in TURNOVERS or is_free_throw):
            if current.acted:
                close(team)
            else:
                current.team = team
        elif team and team != current.team and action in REBOUNDS and rebound_open:
            close(team)
            current.acted = True
        elif action in JUMP_BALLS and current.team and (winner := jump_ball_winner(event)) and winner != current.team and not lost_on_turnover(index):
            if current.events:
                close(winner)
            else:
                current.team = winner
            current.acted = True
        current.events.append(index)

        if not team:
            continue
        missed = str(event.get("description")).startswith("MISS")
        if action in SHOTS:
            current.acted = True
            rebound_open = missed
            if not missed and last_free_throw.get((*_clock_key(event), team), -1) < index:
                basket = (*_clock_key(event), team)
                close(opponent(team))
        elif is_free_throw:
            current.acted = True
            rebound_open = False
            number = _FREE_THROW_NUMBER.search(str(event.get("subType")))
            if number and number[1] == number[2]:
                sub_type = str(event.get("subType")).lower()
                # Only a foul by the other team can give the shooters the ball back
                against = [foul for fouler, foul in fouls.get(_clock_key(event), []) if fouler != team]
                ball_kept = any(kind in text for kind in BALL_KEPT for text in [sub_type, *against])
                if missed:
                    rebound_open = not ball_kept
                elif not ball_kept:
                    close(opponent(team))
        elif action in REBOUNDS and rebound_open:
            current.acted = True
            rebound_open = False
        elif action in TURNOVERS:
            current.acted = True
            close(opponent(team))
    end_period()

    labels: list[tuple[int, str | None]] = [(0, None)] * len(events)
    for number, possession in enumerate(finished, start=1):
        for index in possession.events:
            labels[index] = (number, possession.team)
    return labels


def _activity(event: dict[str, Any], team: str | None, ball: str | None) -> str:
    action = _action_type(event)
    description = str(event.get("description"))
    result = "Missed" if description.startswith("MISS") else "Made"
    if action in SHOTS:
        return f"{result} {'3PT' if action in ('3pt', 'heave') or '3PT' in description else '2PT'}"
    if action in FREE_THROWS:
        return f"{result} Free Throw"
    if action in REBOUNDS:
        return "Offensive Rebound" if team == ball else OPPONENT_REBOUND
    if action in TURNOVERS:
        return "Turnover"
    if action in FOULS:
        if "technical" in f"{event.get('subType')} {event.get('descriptor')}".lower():
            return "Technical Foul"
        return "Offensive Foul" if team == ball else "Defensive Foul"
    if action in VIOLATIONS and "goaltending" in str(event.get("subType")).lower():
        return GOALTENDING
    return "Jump Ball" if action in JUMP_BALLS else action.title()


def _inbound(previous: list[LogEntry], number: int, team: str | None) -> LogEntry:
    """The start of a possession the feed logs nothing for, derived from how the last one ended."""
    last = next((entry for entry in reversed(previous) if entry.activity not in ("Timeout", GOALTENDING)), previous[-1])
    activity = "Inbound"
    if last.team != team and last.activity in SCORES:
        activity = "Inbound after Score"
    elif last.team != team and last.activity == "Turnover":
        activity = "Inbound after Turnover"
    return LogEntry(number, team, activity, previous[-1].index, derived=True)


def _with_kept_ball_inbounds(trace: list[LogEntry], events: list[dict[str, Any]], technical: set[int]) -> list[LogEntry]:
    """Adds an inbound where the team shot its last free throw, kept the ball and play went on."""
    result: list[LogEntry] = []
    kept = False
    for entry in trace:
        if kept and entry.activity != "Timeout":
            if entry.activity != "Offensive Rebound" and entry.activity != OPPONENT_REBOUND and not entry.activity.endswith("Free Throw"):
                result.append(LogEntry(entry.possession, entry.team, "Inbound", result[-1].index, derived=True))
            kept = False
        result.append(entry)
        if entry.activity.endswith("Free Throw"):
            number = _FREE_THROW_NUMBER.search(str(events[entry.index].get("subType")))
            kept = bool(number and number[1] == number[2]) and entry.index not in technical
    return result


def event_log(events: list[dict[str, Any]]) -> list[LogEntry]:
    """One game as an event log, possession by possession.

    Every trace starts with Defensive Rebound, Steal, Jump Ball, Period Start or an inbound. A
    defensive rebound or jump ball is also copied to the end of the possession it finished. A team that keeps the
    ball stays in its trace, with an inbound in the middle. Substitutions and other stoppages are
    dropped, apart from timeouts and the period markers a trace needs.
    """
    team_of = _team_lookup(events)
    jump_ball_winner = _jump_ball_winner(events, team_of)
    technical = _technical_free_throws(events)
    grouped: dict[int, list[int]] = {}
    teams: dict[int, str | None] = {}
    for index, (number, team) in enumerate(assign_possessions(events)):
        grouped.setdefault(number, []).append(index)
        teams[number] = team

    traces: list[list[LogEntry]] = []
    for number, indexes in grouped.items():
        ball = teams[number]
        trace: list[LogEntry] = []
        period_start = period_end = None
        for index in indexes:
            event = events[index]
            action = _action_type(event).lower()
            if action == "period":
                if _is_period_start(event):
                    period_start = index
                else:
                    period_end = index
            elif action not in DROPPED:
                trace.append(LogEntry(number, ball, _activity(event, team_of(event), ball), index))

        trace = _with_kept_ball_inbounds(trace, events, technical)
        first = next((entry for entry in trace if entry.activity != "Timeout"), None)
        previous = traces[-1] if traces else None
        won_jump_ball = bool(first) and first.activity == "Jump Ball" and jump_ball_winner(events[first.index]) == ball
        if period_start is not None:
            if not first or first.activity != "Jump Ball":
                trace.insert(0, LogEntry(number, ball, "Period Start", period_start))
        elif first and first.activity == "Offensive Rebound" and previous and previous[0].team != ball:
            first.activity = "Defensive Rebound"
            previous.append(LogEntry(previous[0].possession, previous[0].team, OPPONENT_REBOUND, first.index, derived=True))
        elif won_jump_ball and previous and previous[0].team != ball and previous[-1].activity not in FINISHED:
            previous.append(LogEntry(previous[0].possession, previous[0].team, OPPONENT_JUMP_BALL, first.index, derived=True))
        elif previous and not won_jump_ball and not (first and first.activity == "Steal"):
            trace.insert(0, _inbound(previous, number, ball))

        if period_end is not None and (not trace or trace[-1].activity not in FINISHED):
            trace.append(LogEntry(number, ball, "Period End", period_end))
        if previous and period_start is None and previous[0].team == ball:
            previous.extend(trace)
        elif trace:
            traces.append(trace)

    for number, trace in enumerate(traces, start=1):
        for entry in trace:
            entry.possession = number
    return [entry for trace in traces for entry in trace]
