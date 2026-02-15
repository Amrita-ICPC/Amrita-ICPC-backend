from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.utils.enums import ContestStatus


@dataclass
class ContestFilters:
    """Filters for querying contests."""

    search_term: str | None = None
    status: ContestStatus | None = None
    is_public: bool | None = None


@dataclass
class CreateContestData:
    """
    Data transfer object for creating contests in the repository layer.

    This class encapsulates the data needed to create a contest without exposing
    the API schema (ContestCreate DTO) to the repository layer, maintaining
    separation of concerns.
    """

    name: str
    description: str | None
    image: str | None
    is_public: bool
    start_time: datetime
    end_time: datetime
    registration_start: datetime
    registration_end: datetime
    max_teams: int | None
    min_team_size: int
    max_team_size: int
    rules: str | None
    scoring_type: str
    created_by: UUID


@dataclass
class UpdateContestData:
    """
    Data transfer object for updating contests in the repository layer.

    This class encapsulates the data needed to update a contest without exposing
    the API schema (ContestUpdate DTO) to the repository layer, maintaining
    separation of concerns. All fields are optional for partial updates.
    """

    name: str | None = None
    description: str | None = None
    image: str | None = None
    is_public: bool | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    registration_start: datetime | None = None
    registration_end: datetime | None = None
    max_teams: int | None = None
    min_team_size: int | None = None
    max_team_size: int | None = None
    rules: str | None = None
    scoring_type: str | None = None
