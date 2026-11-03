"""Export jobs: run one at a time in a background thread, results kept on disk for a while.

Jobs live in memory, so a restart forgets them (and startup deletes their leftover files).
The per-game play-by-play cache survives restarts.
"""

import csv
import json
import logging
import os
import shutil
import threading
import time
import uuid
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import nba
from .models import ExportRequest, Filters, Job
from .possessions import event_log

log = logging.getLogger(__name__)

EXPORTS_DIR = nba.DATA_DIR / "exports"
EXPORT_TTL = float(os.getenv("EXPORT_TTL_HOURS", "24")) * 3600
MAX_GAMES = int(os.getenv("MAX_GAMES", "1500"))

# Play-by-play columns: the event log's own first, then the feed's columns worth filtering on
PBP_COLUMNS = [
    "case_id",
    "activity",
    "timestamp",
    "resource",
    "is_derived",
    "possession_team",
    "team",
    "game_id",
    "game_date",
    "home_team",
    "away_team",
    "event_index",
    "game_seconds",
    "source",
    "period",
    "clock",
    "scoreHome",
    "scoreAway",
    "description",
    "subType",
    "descriptor",
    "qualifiers",
    "shotResult",
    "shotDistance",
    "x",
    "y",
    "area",
    "areaDetail",
    "assistPlayerNameInitial",
    "stealPlayerName",
    "blockPlayerName",
    "foulDrawnPlayerName",
]


class Cancelled(Exception):
    pass


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._cancel: set[str] = set()
        self._lock = threading.Lock()
        # One worker: exports queue up instead of hammering the NBA API in parallel
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="export")
        shutil.rmtree(EXPORTS_DIR, ignore_errors=True)
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def submit(self, request: ExportRequest) -> Job:
        self._cleanup()
        job = Job(id=uuid.uuid4().hex, request=request, created_at=time.time())
        with self._lock:
            self._jobs[job.id] = job
        self._executor.submit(self._run, job)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        self._cleanup()
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def cancel(self, job_id: str) -> None:
        job = self._jobs[job_id]
        if job.status == "queued":
            job.status, job.finished_at = "cancelled", time.time()
        elif job.status == "running":
            self._cancel.add(job_id)

    def path(self, job: Job) -> Path:
        return EXPORTS_DIR / f"{job.id}.{job.request.format}"

    def _cleanup(self) -> None:
        cutoff = time.time() - EXPORT_TTL
        with self._lock:
            expired = [j for j in self._jobs.values() if j.finished_at and j.finished_at < cutoff]
            for job in expired:
                self.path(job).unlink(missing_ok=True)
                del self._jobs[job.id]

    def _run(self, job: Job) -> None:
        if job.status == "cancelled":
            return
        job.status = "running"
        job.message = "Finding games"
        try:
            if job.request.dataset == "games":
                self._export_games(job)
            else:
                self._export_play_by_play(job)
            job.status = "done"
        except Cancelled:
            self.path(job).unlink(missing_ok=True)
            job.status, job.message = "cancelled", None
        except Exception as exc:
            log.exception("Export %s failed", job.id)
            self.path(job).unlink(missing_ok=True)
            job.status, job.error = "failed", f"{type(exc).__name__}: {exc}"
        finally:
            self._cancel.discard(job.id)
            job.finished_at = time.time()

    def _export_games(self, job: Job) -> None:
        rows = nba.find_games(job.request.filters)
        columns = list(rows[0]) if rows else []
        write(rows, columns, job.request.format, self.path(job))
        job.rows = len(rows)
        job.message = f"{len(rows)} team-game rows"
        job.filename = filename(job)

    def _export_play_by_play(self, job: Job) -> None:
        games = nba.game_context(nba.find_games(job.request.filters))
        if len(games) > MAX_GAMES:
            raise ValueError(f"{len(games)} games match, the limit is {MAX_GAMES}. Narrow the filters.")
        job.total = len(games)

        # Pass 1: download each game into a JSON-lines file.
        # Pass 2: write the final file. Memory stays at one game at a time.
        staging = self.path(job).with_suffix(".jsonl")
        skipped: list[str] = []
        from_cache = 0
        try:
            with staging.open("w", encoding="utf-8") as out:
                for game_id, game in sorted(games.items(), key=lambda g: (g[1]["game_date"], g[0])):
                    if job.id in self._cancel:
                        raise Cancelled
                    job.message = f"Game {job.done + 1} of {job.total}" + (f", {from_cache} from cache" if from_cache else "")
                    try:
                        source, events, cached = nba.play_by_play(game_id, cacheable=game["finished"])
                    except Exception as exc:
                        log.warning("Skipping game %s: %s", game_id, exc)
                        skipped.append(game_id)
                        nba.pause()
                    else:
                        from_cache += cached
                        rows = log_rows(game_id, game, source, events)
                        for row in rows:
                            out.write(json.dumps(row) + "\n")
                        job.rows = (job.rows or 0) + len(rows)
                        if not cached:
                            nba.pause()
                    job.done += 1

            if skipped and len(skipped) == len(games):
                raise RuntimeError(f"Every game failed to download, e.g. {skipped[0]}. See the backend logs.")
            job.message = "Writing file"
            write(read_jsonl(staging), PBP_COLUMNS, job.request.format, self.path(job))
        finally:
            staging.unlink(missing_ok=True)

        job.message = f"{job.rows or 0} rows from {len(games) - len(skipped)} games"
        if skipped:
            job.message += f"; {len(skipped)} skipped: {', '.join(skipped[:10])}" + ("…" if len(skipped) > 10 else "")
        job.filename = filename(job)


def log_rows(game_id: str, game: dict[str, Any], source: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The event log rows of one game, trace by trace."""
    timestamps = nba.event_timestamps(events, game["game_date"])
    rows = []
    for entry in event_log(events):
        event = events[entry.index]
        # An inbound only borrows the time and the score: the player and the details aren't its own
        inbound = entry.activity.startswith("Inbound")
        time = timestamps[entry.index] + timedelta(milliseconds=inbound)
        row = ({} if inbound else event) | {
            "case_id": f"{game_id}-{entry.possession:03d}",
            "activity": entry.activity,
            "timestamp": time.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "resource": entry.team if inbound else event.get("playerNameI") or event.get("teamTricode") or entry.team,
            "is_derived": entry.derived,
            "possession_team": entry.team,
            "team": entry.team if inbound else event.get("teamTricode"),
            "game_id": game_id,
            "game_date": game["game_date"],
            "home_team": game.get("home_team"),
            "away_team": game.get("away_team"),
            "event_index": entry.index,
            "game_seconds": nba.game_seconds(event.get("period"), event.get("clock")),
            "source": source,
            "period": event.get("period"),
            "clock": event.get("clock"),
            "scoreHome": event.get("scoreHome"),
            "scoreAway": event.get("scoreAway"),
        }
        rows.append({column: row.get(column) for column in PBP_COLUMNS})
    return rows


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def write(rows: Iterable[dict[str, Any]], columns: list[str], fmt: str, path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        if fmt == "csv":
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                # Lists (qualifiers, personIdsFilter) become "a|b|c"
                writer.writerow({k: "|".join(map(str, v)) if isinstance(v, list) else v for k, v in row.items()})
        else:
            f.write("[")
            for i, row in enumerate(rows):
                f.write(("," if i else "") + "\n" + json.dumps(row, ensure_ascii=False))
            f.write("\n]\n")
    tmp.replace(path)


def filename(job: Job) -> str:
    """e.g. nba_playbyplay_2024-25_regular-season_GSW_vs-LAC_20261025-1430.csv"""
    f: Filters = job.request.filters
    abbreviations = {t["id"]: t["abbreviation"] for t in nba.teams()}
    parts = [
        "nba",
        job.request.dataset,
        f.season,
        f.date_from and f"from-{f.date_from}",
        f.date_to and f"to-{f.date_to}",
        f.season_type and f.season_type.lower().replace(" ", "-"),
        f.team_id and abbreviations.get(f.team_id, str(f.team_id)),
        f.opponent_team_id and "vs-" + abbreviations.get(f.opponent_team_id, str(f.opponent_team_id)),
        f.location and f.location.lower(),
        f.outcome and {"W": "wins", "L": "losses"}[f.outcome],
        datetime.fromtimestamp(job.created_at).strftime("%Y%m%d-%H%M"),
    ]
    return "_".join(p for p in parts if p) + "." + job.request.format
