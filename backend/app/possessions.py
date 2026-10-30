"""Splits a game's play-by-play into possessions, so a possession can be the case of an event log.

A possession ends with a made basket, a last free throw, a turnover, a defensive rebound or the end
of a period. It is worked out from the events because only the live feed has a `possession` field,
and that field counts a few possessions too many (dead balls can split one).
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

SHOTS = {"2pt", "3pt", "heave", "Made Shot", "Missed Shot"}
FREE_THROWS = {"freethrow", "Free Throw"}
TURNOVERS = {"turnover", "Turnover"}
REBOUNDS = {"rebound", "Rebound"}
FOULS = {"foul", "Foul"}

# After these fouls the fouled team shoots and then keeps the ball
BALL_KEPT = ("flagrant", "clear-path", "clear path", "away-from-play", "away from play")

_FREE_THROW_NUMBER = re.compile(r"(\d) of (\d)")


@dataclass
class _Possession:
    team: str | None
    events: list[int] = field(default_factory=list)
    # Something happened that only the team with the ball does, not just subs or a jump ball
    acted: bool = False


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


def assign_possessions(events: list[dict[str, Any]]) -> list[tuple[int, str | None]]:
    """(possession number from 1, team with the ball) for each event, in the order of `events`.

    Substitutions, timeouts and other dead-ball events go with the possession that follows them,
    or with the one before them at the end of a period.
    """
    # The stats feed leaves the team out of team rebounds and team turnovers, but not the location
    by_location = {e["location"]: e["teamTricode"] for e in events if e.get("location") and e.get("teamTricode")}

    def team_of(event: dict[str, Any]) -> str | None:
        return event.get("teamTricode") or by_location.get(event.get("location"))

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
    fouls: dict[tuple[Any, Any], list[str]] = {}
    for event in events:
        if event.get("actionType") in FOULS:
            foul = f"{event.get('subType')} {event.get('descriptor')}".lower()
            fouls.setdefault(_clock_key(event), []).append(foul)

    finished: list[_Possession] = []
    current = _Possession(None)
    period = None
    # A miss is in the air: the next rebound decides who has the ball
    rebound_open = False

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

    for index, event in enumerate(events):
        if event.get("period") != period:
            end_period()
            period = event.get("period")

        action = event.get("actionType")
        team = team_of(event)
        is_free_throw = action in FREE_THROWS and index not in technical

        # Whoever does this has the ball, even if the feed skipped how they got it
        if team and team != current.team and (action in SHOTS or action in TURNOVERS or is_free_throw):
            if current.acted:
                close(team)
            else:
                current.team = team
        elif team and team != current.team and action in REBOUNDS and rebound_open:
            close(team)
            current.acted = True
        current.events.append(index)

        if not team:
            continue
        missed = str(event.get("description")).startswith("MISS")
        if action in SHOTS:
            current.acted = True
            rebound_open = missed
            if not missed and last_free_throw.get((*_clock_key(event), team), -1) < index:
                close(opponent(team))
        elif is_free_throw:
            current.acted = True
            rebound_open = False
            number = _FREE_THROW_NUMBER.search(str(event.get("subType")))
            if number and number[1] == number[2]:
                sub_type = str(event.get("subType")).lower()
                ball_kept = any(kind in text for kind in BALL_KEPT for text in [sub_type, *fouls.get(_clock_key(event), [])])
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
