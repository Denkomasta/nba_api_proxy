"""Calls to the NBA API (via nba_api) and the per-game play-by-play cache."""

import json
import logging
import os
import re
import time
from datetime import date, datetime, timedelta
from itertools import product
from pathlib import Path
from typing import Any

from nba_api.live.nba.endpoints import playbyplay as live_playbyplay
from nba_api.stats.endpoints import leaguegamefinder, playbyplayv3
from nba_api.stats.static import teams as static_teams

from .models import Filters

log = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
CACHE_DIR = DATA_DIR / "cache"
TIMEOUT = int(os.getenv("NBA_TIMEOUT", "30"))
# Pause between NBA requests; stats.nba.com throttles rapid callers
REQUEST_DELAY = float(os.getenv("NBA_REQUEST_DELAY", "0.6"))
RETRIES = 3

# The live feed (with wall-clock timestamps) starts with this season
FIRST_LIVE_SEASON = 2019
FIRST_SEASON = 1996

# The third digit of a game ID, e.g. 0042400101 is a playoff game
GAME_TYPES = {"1": "Pre Season", "2": "Regular Season", "3": "All Star", "4": "Playoffs", "5": "PlayIn", "6": "NBA Cup Final"}


def season_name(start_year: int) -> str:
    """2024 -> "2024-25"."""
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def seasons() -> list[str]:
    """All seasons from 1996-97 up to the current one, newest first."""
    today = date.today()
    current = today.year if today.month >= 10 else today.year - 1
    return [season_name(y) for y in range(current, FIRST_SEASON - 1, -1)]


def teams() -> list[dict[str, Any]]:
    return sorted(
        ({"id": t["id"], "name": t["full_name"], "abbreviation": t["abbreviation"]} for t in static_teams.get_teams()),
        key=lambda t: t["name"],
    )


def _with_retries(call):
    for attempt in range(1, RETRIES + 1):
        try:
            return call()
        except Exception as exc:  # nba_api raises plain requests/JSON errors
            if attempt == RETRIES:
                raise
            log.warning("NBA request failed (attempt %d/%d): %s", attempt, RETRIES, exc)
            time.sleep(2 * attempt)


def find_games(filters: Filters) -> list[dict[str, Any]]:
    """LeagueGameFinder rows: one row per team per game, newest first.

    The endpoint takes one season and one season type at a time, so each pair is one request.
    Each row gets a readable SEASON ("2024-25") and SEASON_TYPE in front of the feed's SEASON_ID ("22024").
    """
    rows: list[dict[str, Any]] = []
    for i, (season, season_type) in enumerate(product(filters.seasons or [None], filters.season_types or [None])):
        if i:
            pause()
        rows += _find_games(filters, season, season_type)
    rows.sort(key=lambda row: (row["GAME_DATE"], row["GAME_ID"]), reverse=True)
    return [
        {"SEASON": season_name(season_start(row["GAME_ID"])), "SEASON_TYPE": game_type(row["GAME_ID"])} | row
        for row in rows
    ]


def _find_games(filters: Filters, season: str | None, season_type: str | None) -> list[dict[str, Any]]:
    mmddyyyy = "%m/%d/%Y"
    finder = _with_retries(
        lambda: leaguegamefinder.LeagueGameFinder(
            player_or_team_abbreviation="T",
            league_id_nullable="00",
            season_nullable=season or "",
            season_type_nullable=season_type or "",
            team_id_nullable=filters.team_id or "",
            vs_team_id_nullable=filters.opponent_team_id or "",
            date_from_nullable=filters.date_from.strftime(mmddyyyy) if filters.date_from else "",
            date_to_nullable=filters.date_to.strftime(mmddyyyy) if filters.date_to else "",
            location_nullable=filters.location or "",
            outcome_nullable=filters.outcome or "",
            timeout=TIMEOUT,
        )
    )
    return finder.get_normalized_dict()["LeagueGameFinderResults"]


def game_context(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per game ID: date, home and away team, and whether it is finished.

    MATCHUP is "GSW vs. LAC" for the home team and "GSW @ LAC" for the away team.
    """
    games: dict[str, dict[str, Any]] = {}
    for row in rows:
        game = games.setdefault(row["GAME_ID"], {"game_date": row["GAME_DATE"], "finished": True})
        game["finished"] = game["finished"] and bool(row["WL"])
        if " vs. " in row["MATCHUP"]:
            game["home_team"], game["away_team"] = row["MATCHUP"].split(" vs. ")
        elif " @ " in row["MATCHUP"]:
            game["away_team"], game["home_team"] = row["MATCHUP"].split(" @ ")
    return games


_CLOCK = re.compile(r"PT(\d+)M([\d.]+)S")


def game_seconds(period: int, clock: str) -> float | None:
    """Elapsed game time: 12-minute quarters, 5-minute overtimes."""
    match = _CLOCK.fullmatch(clock or "")
    if not match or not period:
        return None
    remaining = int(match[1]) * 60 + float(match[2])
    length = 720 if period <= 4 else 300
    before = min(period - 1, 4) * 720 + max(period - 5, 0) * 300
    return round(before + length - remaining, 2)


def event_timestamps(events: list[dict[str, Any]], game_date: str) -> list[datetime]:
    """A UTC time per event, strictly increasing so that sorting by time keeps the feed's order.

    Events are at least 3 ms apart, which leaves room for an inbound 1 ms after the event before it
    and an assist 1 ms before its shot.

    The live feed's `timeActual` can go backwards and repeats within a play. The stats feed has none,
    so its timestamps are midnight on the game date plus the elapsed game time, not the real time.
    """
    midnight = datetime.fromisoformat(f"{game_date}T00:00:00+00:00")
    timestamps = []
    last = None
    for event in events:
        actual = event.get("timeActual")
        time = datetime.fromisoformat(actual) if actual else midnight + timedelta(seconds=game_seconds(event.get("period"), event.get("clock")) or 0)
        last = time if last is None else max(time, last + timedelta(milliseconds=3))
        timestamps.append(last)
    return timestamps


def season_start(game_id: str) -> int:
    # Game IDs look like 0022400061: league "00", type "2", season start year "24"
    yy = int(game_id[3:5])
    return 1900 + yy if yy >= 46 else 2000 + yy


def game_type(game_id: str) -> str | None:
    """"Regular Season", "Playoffs", … from the game ID."""
    return GAME_TYPES.get(game_id[2])


def _download_play_by_play(game_id: str) -> tuple[str, list[dict[str, Any]]]:
    if season_start(game_id) >= FIRST_LIVE_SEASON:
        try:
            data = _with_retries(lambda: live_playbyplay.PlayByPlay(game_id=game_id, timeout=TIMEOUT).get_dict())
            return "live", data["game"]["actions"]
        except Exception as exc:
            log.warning("Live play-by-play failed for %s, falling back to stats: %s", game_id, exc)
    endpoint = _with_retries(lambda: playbyplayv3.PlayByPlayV3(game_id=game_id, timeout=TIMEOUT))
    return "stats", endpoint.get_normalized_dict()["PlayByPlay"]


def play_by_play(game_id: str, cacheable: bool) -> tuple[str, list[dict[str, Any]], bool]:
    """Events of one game, as (source, events, came_from_cache).

    Finished games never change, so they are cached on disk.
    """
    path = CACHE_DIR / f"pbp-{game_id}.json"
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        return cached["source"], cached["events"], True

    source, events = _download_play_by_play(game_id)
    if cacheable and events:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"source": source, "events": events}), encoding="utf-8")
        tmp.replace(path)
    return source, events, False


def pause() -> None:
    time.sleep(REQUEST_DELAY)
