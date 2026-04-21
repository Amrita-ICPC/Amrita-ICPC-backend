from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.utils.enums import ContestStatus, QuestionDifficulty, TeamApprovalMode


class _UnsetType:
    """Sentinel type used to represent fields omitted from patch payloads."""


UNSET = _UnsetType()


@dataclass
class ContestFilters:
    """Filters for querying contests."""

    search_term: str | None = None
    status: ContestStatus | None = None
    is_public: bool | None = None


@dataclass
class ContestQuestionFilters:
    """Filters for querying questions inside a contest."""

    search_term: str | None = None
    difficulty: QuestionDifficulty | None = None
    language_id: int | None = None
    tag_id: UUID | None = None


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
    registration_start: datetime | None
    registration_end: datetime | None
    max_teams: int | None
    min_team_size: int
    max_team_size: int
    rules: str | None
    scoring_type: str
    team_approval_mode: TeamApprovalMode
    audience_ids: list[UUID]
    created_by: UUID


@dataclass
class UpdateContestData:
    """
    Data transfer object for updating contests in the repository layer.

    This class encapsulates the data needed to update a contest without exposing
    the API schema (ContestUpdate DTO) to the repository layer, maintaining
    separation of concerns. All fields are optional for partial updates.
    """

    name: str | None | _UnsetType = UNSET
    description: str | None | _UnsetType = UNSET
    image: str | None | _UnsetType = UNSET
    is_public: bool | None | _UnsetType = UNSET
    start_time: datetime | None | _UnsetType = UNSET
    end_time: datetime | None | _UnsetType = UNSET
    registration_start: datetime | None | _UnsetType = UNSET
    registration_end: datetime | None | _UnsetType = UNSET
    max_teams: int | None | _UnsetType = UNSET
    min_team_size: int | None | _UnsetType = UNSET
    max_team_size: int | None | _UnsetType = UNSET
    rules: str | None | _UnsetType = UNSET
    scoring_type: str | None | _UnsetType = UNSET
    team_approval_mode: TeamApprovalMode | None | _UnsetType = UNSET
