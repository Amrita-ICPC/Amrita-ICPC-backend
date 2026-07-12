from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.repositories.dto.pagination import PaginatedResult
from app.utils.enums import (
    ContestMode,
    ContestQuestionSortBy,
    ContestRunStatus,
    ContestStatus,
    ContestTeamParticipationType,
    QuestionDifficulty,
    SortOrder,
    TeamApprovalMode,
)


class _UnsetType:
    """Sentinel type used to represent fields omitted from patch payloads."""


UNSET = _UnsetType()


@dataclass
class ContestFilters:
    """Filters for querying contests."""

    search_term: str | None = None
    status: ContestStatus | None = None
    run_status: ContestRunStatus | None = None
    is_public: bool | None = None


@dataclass
class ContestQuestionFilters:
    """Filters for querying questions inside a contest."""

    search_term: str | None = None
    difficulty: QuestionDifficulty | None = None
    language_id: int | None = None
    tag_id: UUID | None = None
    tag_name: str | None = None
    sort_by: ContestQuestionSortBy | None = None
    sort_order: SortOrder | None = SortOrder.ASC


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
    end_time: datetime | None
    registration_start: datetime | None
    registration_end: datetime | None
    max_teams: int | None
    min_team_size: int
    max_team_size: int
    rules: str | None
    team_approval_mode: TeamApprovalMode
    contest_mode: ContestMode
    audience_ids: list[UUID]
    created_by: UUID
    duration: int | None
    show_leaderboard_during_contest: bool
    participation_type: ContestTeamParticipationType
    evaluate_on_submit: bool
    max_submission_per_question: int | None
    show_leaderboard: bool
    show_team_submissions: bool
    shuffle_questions: bool


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
    team_approval_mode: TeamApprovalMode | None | _UnsetType = UNSET
    contest_mode: ContestMode | None | _UnsetType = UNSET
    duration: int | None | _UnsetType = UNSET
    show_leaderboard_during_contest: bool | None | _UnsetType = UNSET
    participation_type: ContestTeamParticipationType | None | _UnsetType = UNSET
    evaluate_on_submit: bool | None | _UnsetType = UNSET
    max_submission_per_question: int | None | _UnsetType = UNSET
    show_leaderboard: bool | None | _UnsetType = UNSET
    show_team_submissions: bool | None | _UnsetType = UNSET
    shuffle_questions: bool | None | _UnsetType = UNSET


@dataclass
class ContestQuestionsPaginatedResult(PaginatedResult):
    """
    Paginated result for contest questions with additional metadata for counts.
    """

    easy_count: int = 0
    medium_count: int = 0
    hard_count: int = 0


@dataclass
class ContestsPaginatedResultWithStats(PaginatedResult):
    """
    Paginated result for contests with additional metadata for stats.
    """

    live_count: int = 0
    upcoming_count: int = 0
    completed_count: int = 0


@dataclass
class InstructorDashboardContestRow:
    """
    Raw per-contest data for the instructor dashboard.

    One row per contest accessible to the requesting user (see
    ``ContestRepository._apply_permission_filter``), merged from a handful of
    grouped aggregate queries rather than a per-contest lookup. Run status is
    intentionally not included here -- it's derived at read time via
    ``compute_run_status``, the same utility used everywhere else, so there is
    a single source of truth for LIVE/UPCOMING/ENDED classification.
    """

    id: UUID
    name: str
    image: str | None
    start_time: datetime
    end_time: datetime | None
    status: ContestStatus
    contest_mode: ContestMode
    created_by: UUID | None
    results_published_at: datetime | None
    question_count: int = 0
    registered_teams_count: int = 0
    pending_team_approvals: int = 0
    total_submissions: int = 0
    pending_evaluations: int = 0
