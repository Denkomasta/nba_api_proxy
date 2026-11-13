from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

Dataset = Literal["games", "playbyplay"]
Format = Literal["csv", "json"]
SEASON_TYPES = ["Regular Season", "Playoffs", "PlayIn", "Pre Season", "All Star"]
SeasonType = Literal["Regular Season", "Playoffs", "PlayIn", "Pre Season", "All Star"]
JobStatus = Literal["queued", "running", "done", "failed", "cancelled"]
Season = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}$")]


class Filters(BaseModel):
    seasons: list[Season] = Field(default_factory=list, examples=[["2004-05", "2014-15", "2024-25"]])
    # Empty means every type, including games no single type covers (e.g. the NBA Cup final)
    season_types: list[SeasonType] = Field(default_factory=list, examples=[["Regular Season", "Playoffs"]])
    team_id: int | None = None
    opponent_team_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    location: Literal["Home", "Road"] | None = None
    outcome: Literal["W", "L"] | None = None

    @model_validator(mode="before")
    @classmethod
    def single_values(cls, data: Any) -> Any:
        """Still accept the older `"season": "2024-25"` and `"season_type": "Playoffs"`."""
        if isinstance(data, dict):
            data = dict(data)
            for old, new in [("season", "seasons"), ("season_type", "season_types")]:
                value = data.pop(old, None)
                if value and not data.get(new):
                    data[new] = [value]
        return data

    @model_validator(mode="after")
    def check(self) -> "Filters":
        self.seasons = sorted(set(self.seasons))
        self.season_types = [t for t in SEASON_TYPES if t in self.season_types]
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
