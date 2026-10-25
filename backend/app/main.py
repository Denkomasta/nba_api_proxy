import logging

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse

from . import nba
from .jobs import MAX_GAMES, JobManager
from .models import ExportRequest, Job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="NBA API proxy", docs_url="/api/docs", openapi_url="/api/openapi.json")
jobs = JobManager()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/options")
def options() -> dict:
    """Values for the filter form."""
    return {
        "seasons": nba.seasons(),
        "season_types": nba.SEASON_TYPES,
        "teams": nba.teams(),
        "first_live_season": f"{nba.FIRST_LIVE_SEASON}-{(nba.FIRST_LIVE_SEASON + 1) % 100:02d}",
        "max_games": MAX_GAMES,
    }


@app.get("/api/exports")
def list_exports() -> list[Job]:
    return jobs.list()


@app.post("/api/exports", status_code=status.HTTP_202_ACCEPTED)
def create_export(request: ExportRequest) -> Job:
    return jobs.submit(request)


def _job(job_id: str) -> Job:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export not found (they are kept for a limited time)")
    return job


@app.get("/api/exports/{job_id}")
def get_export(job_id: str) -> Job:
    return _job(job_id)


@app.post("/api/exports/{job_id}/cancel")
def cancel_export(job_id: str) -> Job:
    jobs.cancel(_job(job_id).id)
    return _job(job_id)


@app.get("/api/exports/{job_id}/download")
def download_export(job_id: str) -> FileResponse:
    job = _job(job_id)
    if job.status != "done":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Export is {job.status}")
    media_type = "text/csv" if job.request.format == "csv" else "application/json"
    return FileResponse(jobs.path(job), media_type=media_type, filename=job.filename)
