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
| **Games** | `LeagueGameFinder` | team per game (each game appears twice when no team is selected), with box score totals, a readable `SEASON` and `SEASON_TYPE` | one request per season and season type, a few seconds |
| **Play-by-play** | NBA live feed (`cdn.nba.com`) from 2019-20, `PlayByPlayV3` (stats.nba.com) before that | event | one request per game, about 1–3 s each |

Filters: seasons, season types, date range, team, opponent, home/away, win/loss. You need at least one
season or a start date. You can pick any number of seasons, e.g. 2004-05, 2014-15 and 2024-25 to compare
decades, and any number of season types, e.g. Regular Season and Playoffs. They go into one file, and each
row says which season and season type it's from. With no season type selected you get every game,
including preseason, All-Star games and the NBA Cup final.

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
| `game_id`, `season`, `season_type`, `home_team`, `away_team` | Game context. `season` is e.g. `2024-25`, `season_type` e.g. `Playoffs` |
| `game_seconds` | Elapsed game time: 12-minute quarters, 5-minute overtimes |
| `period` | The quarter or overtime |
| `scoreHome`, `scoreAway` | The score. Stats feed: only on rows where it changes or a period starts or ends |
| `subType` | The kind of shot, foul or turnover, e.g. `Driving Layup Shot` |
| `descriptor` | More detail on the shot or foul, e.g. `driving`, `shooting`. Live feed only |
| `qualifiers` | Play context, e.g. `fastbreak`, `2ndchance`. Live feed only. In CSV, values are joined with `\|` |
| `shotDistance` | Distance of the shot in feet. Stats feed: `0` on every other event, and on some shots where the distance is missing |
| `area` | Court zone, e.g. `Restricted Area`. Live feed only |
| `foulDrawnPlayerName` | The player who was fouled. Live feed only |

A trace starts with how the team got the ball and ends with how the possession finished. `Goaltending`
is a defender illegally touching a shot, so the basket counts. It stays with that basket, right after it:

| | Activities |
|---|---|
| **Start** | `Defensive Rebound`, `Inbound after Score`, `Inbound after Turnover`, `Steal`, `Jump Ball`, `Period Start` |
| **During** | `Assist`, `Made 2PT`, `Missed 2PT`, `Made 3PT`, `Missed 3PT`, `Made Free Throw`, `Missed Free Throw`, `Offensive Rebound`, `Block`, `Defensive Foul`, `Offensive Foul`, `Technical Foul`, `Violation`, `Goaltending`, `Jump Ball`, `Timeout`, `Inbound` |
| **End** | `Made 2PT`, `Made 3PT`, `Made Free Throw`, `Goaltending`, `Turnover`, `Opponent Defensive Rebound`, `Opponent Jump Ball`, `Period End` |

Rows with `is_derived` set to `True` are added to give every trace these boundaries:

- **`Opponent Defensive Rebound`** and **`Opponent Jump Ball`** are copies of the real rebound or jump ball
  that starts the next possession, so filter on `is_derived` when counting.
- **`Assist`** comes 1 ms before the made shot it belongs to, because the feed only records the assist on the
  shot's row. Its `resource` is the player who gave it, and its score already includes the basket.
- **`Inbound…`** is inferred, because the feed doesn't log inbound passes. It takes its time from the end
  of the previous possession and has no player. `Inbound` without a reason appears mid-trace, where the same team keeps the ball, for example after a
  transition take free throw. A team that keeps the ball always stays in the same possession.

Substitutions, ejections and game end markers are left out. `Period Start` and `Period End` are only kept
where they open or close a trace. A few traces don't follow these boundaries because of the feed's order
of events at the same clock. Possessions are worked out in `backend/app/possessions.py`, the same way for
both feeds. Timestamps before 2019-20 are built from the game clock, so their durations leave out
stoppages. If one export mixes seasons from before and after 2019-20, compare durations with
`game_seconds`, not `timestamp`. On those older jump balls, `team` and `resource` show the
first jumper, not the winner.

### How exports run

- An export runs in the background. The page shows its progress, and the Download button appears when
  it's done. You can close the page while it runs.
- Exports run **one at a time**. Others wait in the queue, so the NBA API doesn't throttle you.
  A full regular season (1,230 games) takes roughly 30–60 minutes the first time, so six seasons take
  a few hours. Seasons you already exported come from the cache.
- A play-by-play export refuses more than `MAX_GAMES` games (1,500 by default) in any one season.
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
| `POST` | `/api/exports` | Start an export: `{"dataset": "playbyplay", "format": "csv", "filters": {"seasons": ["2004-05", "2024-25"], "season_types": ["Regular Season", "Playoffs"], "team_id": 1610612744}}` |
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
