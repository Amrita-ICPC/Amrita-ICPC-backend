"""Response schemas for the instructor dashboard endpoint (GET /instructors/dashboard)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import ContestMode, ContestRunStatus, ContestStatus


class InstructorDashboardSummary(BaseModel):
    """High-level counts driving the dashboard's summary cards."""

    live_contests: int = Field(
        ..., description="Accessible contests whose derived run status is LIVE"
    )
    upcoming_contests: int = Field(
        ..., description="Accessible contests whose derived run status is UPCOMING"
    )
    completed_contests: int = Field(
        ..., description="Accessible contests whose derived run status is ENDED"
    )
    pending_team_approvals: int = Field(
        ..., description="Teams awaiting approval across accessible contests"
    )
    pending_evaluations: int = Field(
        ...,
        description=(
            "Ended accessible contests that still have unevaluated submissions"
        ),
    )
    results_ready_to_publish: int = Field(
        ...,
        description="Ended contests whose evaluation is complete but not yet published",
    )
    question_banks: int = Field(
        ..., description="Question banks owned by or shared with the current user"
    )


class InstructorDashboardAttentionItem(BaseModel):
    """A single actionable item surfaced on the dashboard."""

    type: Literal[
        "TEAM_APPROVAL",
        "MISSING_QUESTIONS",
        "PENDING_EVALUATION",
        "RESULTS_READY",
    ] = Field(..., description="Category of the attention item")
    contest_id: UUID = Field(..., description="Contest this item relates to")
    contest_name: str = Field(..., description="Contest name, for display")
    count: int | None = Field(
        default=None,
        description="Relevant count when applicable (e.g. teams/submissions)",
    )
    message: str = Field(..., description="Human-readable summary of the issue")


class InstructorDashboardContest(BaseModel):
    """Lightweight contest summary used within the dashboard's contest groups."""

    id: UUID = Field(..., description="Contest ID")
    name: str = Field(..., description="Contest name")
    image: str | None = Field(default=None, description="Contest image URL")
    start_time: datetime = Field(..., description="Contest start time (UTC)")
    end_time: datetime | None = Field(
        default=None, description="Contest end time (UTC)"
    )
    run_status: ContestRunStatus = Field(
        ..., description="Derived temporal run-state (UPCOMING / LIVE / ENDED)"
    )
    status: ContestStatus = Field(..., description="Contest lifecycle status")
    contest_mode: ContestMode = Field(
        ..., description="Contest mode (individual or team)"
    )
    question_count: int = Field(
        ..., description="Number of questions added to the contest"
    )
    registered_teams_count: int = Field(
        ..., description="Confirmed and approved teams registered in the contest"
    )
    pending_team_approvals: int = Field(
        ..., description="Teams awaiting approval in this contest"
    )
    total_submissions: int = Field(
        ..., description="Total submissions made in the contest"
    )
    results_published_at: datetime | None = Field(
        default=None, description="When results were published, if at all"
    )
    created_by_current_user: bool = Field(
        ..., description="Whether the current user created this contest"
    )

    model_config = ConfigDict(from_attributes=True)


class InstructorDashboardBank(BaseModel):
    """Lightweight bank summary used within the dashboard's recent banks list."""

    id: UUID = Field(..., description="Bank ID")
    name: str = Field(..., description="Bank name")
    description: str | None = Field(default=None, description="Bank description")
    question_count: int = Field(..., description="Number of questions in the bank")
    updated_at: datetime = Field(..., description="Last update time (UTC)")
    is_owner: bool = Field(..., description="Whether the current user owns this bank")

    model_config = ConfigDict(from_attributes=True)


class InstructorDashboardContestGroups(BaseModel):
    """Contests grouped by derived run-status, each capped at contest_limit."""

    live: list[InstructorDashboardContest] = Field(default_factory=list)
    upcoming: list[InstructorDashboardContest] = Field(default_factory=list)
    completed: list[InstructorDashboardContest] = Field(default_factory=list)


class InstructorDashboardResponse(BaseModel):
    """Full payload for GET /instructors/dashboard."""

    summary: InstructorDashboardSummary
    needs_attention: list[InstructorDashboardAttentionItem] = Field(
        default_factory=list
    )
    contests: InstructorDashboardContestGroups
    recent_banks: list[InstructorDashboardBank] = Field(default_factory=list)
