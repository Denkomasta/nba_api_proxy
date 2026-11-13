from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

Dataset = Literal["games", "playbyplay"]
Format = Literal["csv", "json"]
SeasonType = Literal["Regular Season", "Playoffs", "PlayIn", "Pre Season", "All Star"]
JobStatus = Literal["queued", "running", "done", "failed", "cancelled"]
Season = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}$")]


class Filters(BaseModel):
    seasons: list[Season] = Field(default_factory=list, examples=[["2004-05", "2014-15", "2024-25"]])
    season_type: SeasonType | None = None
    team_id: int | None = None
    opponent_team_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    location: Literal["Home", "Road"] | None = None
    outcome: Literal["W", "L"] | None = None

    @model_validator(mode="before")
    @classmethod
    def single_season(cls, data: Any) -> Any:
        """Still accept the older `"season": "2024-25"`."""
        if isinstance(data, dict) and "season" in data:
            data = dict(data)
            season = data.pop("season")
            if season and not data.get("seasons"):
                data["seasons"] = [season]
        return data

    @model_validator(mode="after")
    def check(self) -> "Filters":
        self.seasons = sorted(set(self.seasons))
        if not self.seasons and not self.date_from:
            raise ValueError("Pick a season or a start date")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("The start date is after the end date")
        if self.team_id and self.team_id == self.opponent_team_id:
            raise ValueError("Team and opponent are the same")
        return self


class ExportRequest(BaseModel):
    dataset: Dataset
    format: Format = "csv"
    filters: Filters


class Job(BaseModel):
    id: str
    request: ExportRequest
    status: JobStatus = "queued"
    created_at: float
    finished_at: float | None = None
    # Play-by-play: games processed so far / games matching the filters
    done: int = 0
    total: int | None = None
    rows: int | None = None
    message: str | None = None
    error: str | None = None
    filename: str | None = None
