from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.utils.enums import QuestionDifficulty, SubmissionStatus


@dataclass
class ContestAnalyticsRaw:
    """Raw aggregate counts of submission statuses in a contest."""

    total_submissions: int
    accepted: int
    wrong_answer: int
    time_limit_exceeded: int
    runtime_error: int
    compilation_error: int
    memory_limit_exceeded: int
    system_error: int


@dataclass
class ProblemHealthRaw:
    """Raw counts and metadata for a contest question."""

    id: UUID
    title: str
    difficulty: QuestionDifficulty
    attempts: int
    accepted: int
    system_errors: int


@dataclass
class TeamPerformanceRaw:
    """Raw performance and activity metrics for a participating team."""

    id: UUID
    name: str
    solved: int
    attempted: int
    total_attempts: int
    accepted_attempts: int
    last_activity_at: datetime | None


@dataclass
class RecentSubmissionRaw:
    """Raw detail information for a single recent submission."""

    id: UUID
    user_id: UUID
    user_name: str
    team_id: UUID | None
    team_name: str | None
    question_id: UUID
    question_title: str
    language_name: str
    status: SubmissionStatus
    created_at: datetime


@dataclass
class ContestDashboardRawData:
    """Composite raw data structure returned by the repository for the dashboard."""

    analytics: ContestAnalyticsRaw
    problem_health: list[ProblemHealthRaw]
    team_performance: list[TeamPerformanceRaw]
    recent_submissions: list[RecentSubmissionRaw]
