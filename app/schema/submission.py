"""Pydantic schemas for the admin/instructor contest submission dashboard."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import QuestionDifficulty, SubmissionStatus


class ContestAnalyticsSchema(BaseModel):
    """Aggregate verdict breakdown for the entire contest."""

    total_submissions: int = Field(
        ..., description="Total number of submissions in the contest"
    )
    accepted: int = Field(..., description="Number of accepted submissions (AC)")
    wrong_answer: int = Field(
        ..., description="Number of wrong answer submissions (WA)"
    )
    time_limit_exceeded: int = Field(
        ..., description="Number of time limit exceeded submissions (TLE)"
    )
    runtime_error: int = Field(
        ..., description="Number of runtime error submissions (RE)"
    )
    compilation_error: int = Field(
        ..., description="Number of compilation error submissions (CE)"
    )
    memory_limit_exceeded: int = Field(
        ..., description="Number of memory limit exceeded submissions (MLE)"
    )
    system_error: int = Field(
        ..., description="Number of system error submissions (SYSTEM_ERROR)"
    )

    model_config = ConfigDict(from_attributes=True)


class ProblematicQuestionSchema(BaseModel):
    """Question with potentially low acceptance rate or system errors."""

    id: UUID = Field(..., description="Unique identifier of the question")
    title: str = Field(..., description="Title of the question")
    difficulty: QuestionDifficulty = Field(
        ..., description="Difficulty level of the question"
    )
    attempts: int = Field(..., description="Number of attempts on this question")
    acceptance_rate: float = Field(
        ..., description="Acceptance rate of the question as a percentage"
    )

    model_config = ConfigDict(from_attributes=True)


class NeedsAttentionSchema(BaseModel):
    """Overview of elements requiring instructor attention."""

    system_errors: int = Field(
        ..., description="Total system errors across the contest"
    )
    problematic_questions: list[ProblematicQuestionSchema] = Field(
        ..., description="List of questions that may need attention"
    )

    model_config = ConfigDict(from_attributes=True)


class TeamPerformanceSchema(BaseModel):
    """Performance metrics for teams participating in the contest."""

    id: UUID = Field(..., description="Unique identifier of the team")
    name: str = Field(..., description="Name of the team")
    solved: int = Field(..., description="Number of questions solved by the team")
    attempted: int = Field(..., description="Number of questions attempted by the team")
    failed: int = Field(..., description="Number of failed attempts by the team")
    acceptance_rate: float = Field(
        ..., description="Acceptance rate of the team as a percentage"
    )
    last_activity_at: Optional[datetime] = Field(
        None, description="Timestamp of the team's last activity"
    )

    model_config = ConfigDict(from_attributes=True)


class ProblemHealthSchema(BaseModel):
    """Health and submission metrics for a contest problem."""

    id: UUID = Field(..., description="Unique identifier of the question")
    title: str = Field(..., description="Title of the question")
    difficulty: QuestionDifficulty = Field(
        ..., description="Difficulty level of the question"
    )
    attempts: int = Field(..., description="Number of attempts on this question")
    accepted: int = Field(..., description="Number of accepted submissions")
    acceptance_rate: float = Field(
        ..., description="Acceptance rate of the question as a percentage"
    )
    system_errors: int = Field(
        ..., description="Number of system errors on this question"
    )

    model_config = ConfigDict(from_attributes=True)


class SubmissionUserSchema(BaseModel):
    """Minimal details of the user who submitted."""

    id: UUID = Field(..., description="Unique identifier of the user")
    name: str = Field(..., description="Name of the user")

    model_config = ConfigDict(from_attributes=True)


class SubmissionTeamSchema(BaseModel):
    """Minimal details of the team associated with the submission."""

    id: UUID = Field(..., description="Unique identifier of the team")
    name: str = Field(..., description="Name of the team")

    model_config = ConfigDict(from_attributes=True)


class SubmissionQuestionSchema(BaseModel):
    """Minimal details of the question submitted for."""

    id: UUID = Field(..., description="Unique identifier of the question")
    title: str = Field(..., description="Title of the question")

    model_config = ConfigDict(from_attributes=True)


class RecentSubmissionSchema(BaseModel):
    """Details of a single recent submission."""

    id: UUID = Field(..., description="Unique identifier of the submission")
    submitted_by: SubmissionUserSchema = Field(
        ..., description="Details of the user who submitted"
    )
    team: Optional[SubmissionTeamSchema] = Field(
        None, description="Details of the team, if any"
    )
    question: SubmissionQuestionSchema = Field(
        ..., description="Details of the question submitted for"
    )
    language: str = Field(..., description="Programming language name")
    status: SubmissionStatus = Field(..., description="Status of the submission")
    created_at: datetime = Field(
        ..., description="Timestamp when the submission was created"
    )

    model_config = ConfigDict(from_attributes=True)


class ContestDashboardResponse(BaseModel):
    """Comprehensive schema for the contest submission and analytics dashboard."""

    contest_analytics: ContestAnalyticsSchema = Field(
        ..., description="Contest submissions aggregate analytics"
    )
    needs_attention: NeedsAttentionSchema = Field(
        ..., description="Items needing attention or review"
    )
    team_performance: list[TeamPerformanceSchema] = Field(
        ..., description="Performance metrics of teams"
    )
    problem_health: list[ProblemHealthSchema] = Field(
        ..., description="Health metrics of problems"
    )
    recent_submissions: list[RecentSubmissionSchema] = Field(
        ..., description="Most recent submissions list"
    )

    model_config = ConfigDict(from_attributes=True)
