# NBA API proxy

A small web app for downloading NBA data as CSV or JSON. Pick filters in the browser and the backend
fetches the data from NBA.com through [`nba_api`](https://github.com/swar/nba_api). It was built for a
process mining assignment, so play-by-play exports are shaped as an event log.

## Quick start

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
git clone https://github.com/Denkomasta/nba_api_proxy.git
cd nba_api_proxy
docker compose up -d --build
```

Open <http://localhost:8765>. To stop it, run `docker compose down`. The cache is kept in a Docker
volume; add `-v` to delete it. To update after a `git pull`, run `docker compose up -d --build` again.
To change the port or other settings, copy `.env.example` to `.env` and edit it.

**Run it on your own computer, not on a server.** stats.nba.com and cdn.nba.com don't answer requests
from cloud hosting IPs (AWS, Azure, Hetzner, …). Home and university connections work.

- **Backend:** Python, FastAPI and `nba_api` (`backend/`)
- **Frontend:** React, TypeScript, Tailwind CSS, [`denval-ui`](https://github.com/Denkomasta/denval-ui) and Vite (`frontend/`), served by nginx, which also proxies `/api`

## Datasets

| Dataset | Source | One row per | Speed |
|---------|--------|-------------|-------|
| **Games** | `LeagueGameFinder` | team per game (each game appears twice when no team is selected), with box score totals | one request, a few seconds |
| **Play-by-play** | NBA live feed (`cdn.nba.com`) from 2019-20, `PlayByPlayV3` (stats.nba.com) before that | event | one request per game, about 1–3 s each |

Filters: season, season type, date range, team, opponent, home/away, win/loss. You need at least a
season or a start date.

### Play-by-play as an event log

Each row belongs to one possession, which is the case. Import these three columns as the event log:

| Column | Meaning |
|--------|---------|
| `case_id` | The possession, e.g. `0022500001-042` |
| `activity` | What happened, named from the side of the team with the ball, e.g. `Made 2PT` |
| `timestamp` | UTC, strictly increasing within a game. Live feed: `timeActual`, nudged forward where it repeats or goes backwards. Stats feed (before 2019-20): midnight on the game date plus `game_seconds`, so not the real time of day. |

The other columns describe the event:

| Column | Meaning |
|--------|---------|
| `resource` | The player, or the team when no player is involved |
| `is_derived` | `True` if the row isn't an event of its own in the NBA feed (see below) |
| `possession_team`, `team` | Team with the ball, and team that did this event |
| `game_id`, `game_date`, `home_team`, `away_team` | Game context |
| `event_index` | Position of the source event within the game's feed |
| `game_seconds` | Elapsed game time: 12-minute quarters, 5-minute overtimes |
| `source` | `live` or `stats`, i.e. which feed the game came from |

They are followed by a selection of the feed's columns: `period`, `clock`, `scoreHome`, `scoreAway`,
`description`, `subType`, `descriptor`, `qualifiers`, `shotResult`, `shotDistance`, `x`, `y`, `area`,
`areaDetail`, `assistPlayerNameInitial`, `stealPlayerName`, `blockPlayerName` and
`foulDrawnPlayerName`. In CSV, list values such as `qualifiers` are joined with `|`.

A trace starts with how the team got the ball and ends with how the possession finished:

| | Activities |
|---|---|
| **Start** | `Defensive Rebound`, `Inbound after Score`, `Inbound after Turnover`, `Steal`, `Jump Ball`, `Period Start` |
| **During** | `Made 2PT`, `Missed 2PT`, `Made 3PT`, `Missed 3PT`, `Made Free Throw`, `Missed Free Throw`, `Offensive Rebound`, `Block`, `Defensive Foul`, `Offensive Foul`, `Technical Foul`, `Violation`, `Jump Ball`, `Timeout`, `Inbound` |
| **End** | `Made 2PT`, `Made 3PT`, `Made Free Throw`, `Turnover`, `Opponent Defensive Rebound`, `Period End` |

Rows with `is_derived` set to `True` are added to give every trace these boundaries:

- **`Opponent Defensive Rebound`** is a copy of the real rebound that starts the next possession. It has
  the same `event_index`, so filter on `is_derived` when counting rebounds.
- **`Inbound…`** is inferred, because the feed doesn't log inbound passes. It takes its time from the end
  of the previous possession and has no player. `Inbound` without a reason appears mid-trace, where the same team keeps the ball, for example after a
  transition take free throw. A team that keeps the ball always stays in the same possession.

Substitutions, ejections and game end markers are left out. `Period Start` and `Period End` are only kept
where they open or close a trace. A few traces don't follow these boundaries because of the feed's order
of events at the same clock. Possessions are worked out in `backend/app/possessions.py`, the same way for
both feeds. The stats feed may log some events differently, such as steals, so keep one export within
one era.

### How exports run

- An export runs in the background. The page shows its progress, and the Download button appears when
  it's done. You can close the page while it runs.
- Exports run **one at a time**. Others wait in the queue, so the NBA API doesn't throttle you.
  A full regular season (1,230 games) takes roughly 30–60 minutes the first time.
- Finished games are **cached on disk**, so exporting the same games again takes seconds.
- A game that fails to download is skipped and listed in the export's message.
- Finished files stay downloadable for 24 hours. A backend restart forgets the list of exports, but
  the cache is kept.

## Development

The backend needs Python 3.12+ and the frontend needs Node 24.

```bash
# Backend: http://localhost:8000/api/docs
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows; on Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend: http://localhost:5173 (proxies /api to the backend)
cd frontend
npm install
npm run dev
npm run lint
npm run build
```

In development the cache and exports go to `backend/data/`, which is git-ignored.

### API

| Method | Path | |
|--------|------|-|
| `GET` | `/api/options` | Seasons, season types, teams |
| `GET` | `/api/exports` | All exports from the last 24 h |
| `POST` | `/api/exports` | Start an export: `{"dataset": "playbyplay", "format": "csv", "filters": {"season": "2024-25", "team_id": 1610612744}}` |
| `GET` | `/api/exports/{id}` | Status and progress |
| `POST` | `/api/exports/{id}/cancel` | Cancel |
| `GET` | `/api/exports/{id}/download` | The file |

The interactive docs are at `/api/docs`. You can also script the API directly without the UI.

## Docker setup

`compose.yaml` builds two images from this repo:

- **frontend:** nginx serves the built SPA and proxies `/api` to the backend. It's published only on
  `127.0.0.1:${PORT}`, so other devices on your network can't reach it.
- **backend:** private to the stack. Its cache and exports live in the `data` volume.

Useful commands:

```bash
docker compose logs -f backend      # download failures, skipped games
docker compose down -v              # stop and delete the cache
```

If stats.nba.com doesn't answer your connection either (exports fail with timeouts), set
`NBA_API_PROXY` in `.env` to an HTTP proxy it accepts.

## CI

On every push to `main` and every pull request, [`.github/workflows/ci.yml`](.github/workflows/ci.yml)
lints and builds the frontend, checks that the backend imports, and builds both Docker images.
Nothing is deployed.
