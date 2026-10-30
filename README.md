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

These columns come first, followed by every raw column the NBA feed returns:

| Column | Meaning |
|--------|---------|
| `game_id` | Case ID for one case per game |
| `possession_id` | Case ID for one case per possession, e.g. `0022500001-042` |
| `possession_team` | Team with the ball in that possession |
| `game_date`, `home_team`, `away_team` | Game context |
| `event_index` | Position of the event within the game (0, 1, 2, …). Use it as the order. |
| `game_seconds` | Elapsed game time: 12-minute quarters, 5-minute overtimes |
| `source` | `live` or `stats`, i.e. which feed the game came from |

Useful raw columns:

- `actionType` / `subType` / `descriptor`: candidates for the activity
- `timeActual`: wall-clock timestamp (UTC), **live feed only, so 2019-20 onward**. For older games use `game_seconds`.
- `teamTricode`, `playerNameI`, `personId`: resources
- `period`, `clock`, `scoreHome`, `scoreAway`, `shotResult`, `description`

The two feeds name some values differently. For example, live has `actionType` `2pt` or `3pt` plus a
`shotResult`, while stats has `Made Shot` or `Missed Shot`. Keep one export within one era, or map the
values when you analyze the data. In CSV, list values such as `qualifiers` and `personIdsFilter` are
joined with `|`.

A possession ends with a made basket, a last free throw, a turnover, a defensive rebound or the end of
a period, so an offensive rebound continues it. Possessions are worked out from the events in
`backend/app/possessions.py`, the same way for both feeds, and the raw `possession` column of the live
feed is kept next to them. Substitutions, timeouts and other dead-ball events go with the possession
that follows them, so filter them out if they would clutter the process model.

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
