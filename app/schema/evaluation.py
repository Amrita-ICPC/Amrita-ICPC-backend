from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.question import Submission
from app.schema.question import QuestionTestCaseResponse
from app.utils.enums import EvaluationScope, EvaluationStatus


class EvaluationTriggerRequest(BaseModel):
    """Request body for triggering a contest evaluation.

    ``scope`` selects what gets (re-)evaluated:
    - ALL: every submission in the contest.
    - TEAMS: only submissions from the given ``team_ids``.
    - QUESTIONS: only submissions for the given ``question_ids``.
    - STUDENTS: only submissions from the given ``student_ids`` (contest team member ids).
    """

    scope: EvaluationScope = Field(
        default=EvaluationScope.ALL,
        description="What to evaluate: ALL/TEAMS/QUESTIONS/STUDENTS",
    )
    team_ids: list[UUID] | None = Field(
        default=None, description="Contest team ids to evaluate (required for TEAMS)"
    )
    question_ids: list[UUID] | None = Field(
        default=None, description="Question ids to evaluate (required for QUESTIONS)"
    )
    student_ids: list[UUID] | None = Field(
        default=None,
        description="Contest team member ids to evaluate (required for STUDENTS)",
    )

    @model_validator(mode="after")
    def validate_scope_selection(self):
        if self.scope == EvaluationScope.TEAMS and not self.team_ids:
            raise ValueError("team_ids is required when scope is TEAMS")
        if self.scope == EvaluationScope.QUESTIONS and not self.question_ids:
            raise ValueError("question_ids is required when scope is QUESTIONS")
        if self.scope == EvaluationScope.STUDENTS and not self.student_ids:
            raise ValueError("student_ids is required when scope is STUDENTS")
        return self


class EvaluationResponse(BaseModel):
    """Schema for evaluation response."""

    id: UUID = Field(..., description="Evaluation ID")
    contest_id: UUID = Field(..., description="Contest ID")
    is_evaluated: bool = Field(..., description="Whether the evaluation is completed")
    total_submissions: int = Field(..., description="Total submissions to process")
    processed_submissions: int = Field(..., description="Processed submissions count")
    scope: EvaluationScope = Field(
        default=EvaluationScope.ALL, description="What this run evaluated"
    )
    team_ids: list[UUID] | None = Field(
        default=None, description="Contest team ids evaluated, when scope is TEAMS"
    )
    question_ids: list[UUID] | None = Field(
        default=None, description="Question ids evaluated, when scope is QUESTIONS"
    )
    student_ids: list[UUID] | None = Field(
        default=None,
        description="Contest team member ids evaluated, when scope is STUDENTS",
    )
    created_at: datetime = Field(..., description="Creation time (UTC)")
    created_by: UUID = Field(..., description="Creator user ID")

    model_config = ConfigDict(from_attributes=True)


class EvaluationStatusResponse(BaseModel):
    """Schema for contest evaluation status polling."""

    id: UUID = Field(..., description="Evaluation ID")
    contest_id: UUID = Field(..., description="Contest ID")
    status: EvaluationStatus = Field(
        ..., description="Evaluation status (PENDING, RUNNING, COMPLETED)"
    )
    total_submissions: int = Field(..., description="Total submissions to evaluate")
    processed_submissions: int = Field(
        ..., description="Number of evaluated submissions"
    )
    scope: EvaluationScope = Field(
        default=EvaluationScope.ALL, description="What this run evaluated"
    )
    team_ids: list[UUID] | None = Field(
        default=None, description="Contest team ids evaluated, when scope is TEAMS"
    )
    question_ids: list[UUID] | None = Field(
        default=None, description="Question ids evaluated, when scope is QUESTIONS"
    )
    student_ids: list[UUID] | None = Field(
        default=None,
        description="Contest team member ids evaluated, when scope is STUDENTS",
    )

    model_config = ConfigDict(from_attributes=True)


class ContestSubmissionContext(BaseModel):
    """Pydantic schema for the contest submission context fetched during evaluation."""

    contest_id: UUID
    team_id: UUID | None = None
    contest_team_member_id: UUID | None = None


class TokenEntry(BaseModel):
    """One testcase's Judge0 token, captured at SUBMIT time.

    ``token`` is None when Judge0 rejected that particular testcase at submit
    time (e.g. malformed payload); PERSIST treats such entries as failed.
    """

    token: str | None = Field(
        default=None, description="Judge0 submission token for this testcase"
    )
    testcase_id: UUID = Field(
        ..., description="SubmissionTestCase id this token belongs to"
    )


class EvalRef(BaseModel):
    """Identifies the bulk evaluation run a submission belongs to, if any."""

    contest_id: UUID = Field(..., description="Contest being bulk-evaluated")
    evaluation_id: UUID = Field(..., description="Evaluation run id (supersede key)")


class SubmissionPendingContext(BaseModel):
    """The full SUBMIT -> PERSIST handoff, stored as the Redis ``eval:sub:{id}`` value.

    This is the single typed contract for that key: SUBMIT writes it, the Beat
    poller reads ``tokens``/``deadline`` to decide when to dispatch PERSIST, and
    PERSIST consumes the rest to score and finalize the submission. No other
    shape should ever be written to this key.
    """

    submission_id: UUID
    question_id: UUID
    max_score: int
    reevaluation: bool = False
    publish_events: bool = True
    tokens: list[TokenEntry] = Field(default_factory=list)
    eval_ref: EvalRef | None = Field(
        default=None, description="Set for bulk contest evaluation, else None"
    )
    sse: ContestSubmissionContext | None = Field(
        default=None, description="SSE publish context for student-facing events"
    )
    deadline: float = Field(
        ...,
        description="Epoch seconds after which the poller force-persists this submission",
    )


class EvaluationRecord(BaseModel):
    """Immutable bulk-evaluation metadata stored at ``contests:{id}:evaluation``.

    Progress (processed/active counters) is tracked separately via atomic Redis
    counters, not on this record, so this value never needs rewriting mid-run.
    """

    id: UUID = Field(..., description="Evaluation run id")
    contest_id: UUID = Field(..., description="Contest being evaluated")
    total_submissions: int = Field(
        ..., description="Total submissions this run will process"
    )
    scope: EvaluationScope = Field(
        default=EvaluationScope.ALL, description="What this run evaluates"
    )
    team_ids: list[UUID] | None = Field(
        default=None, description="Contest team ids evaluated, when scope is TEAMS"
    )
    question_ids: list[UUID] | None = Field(
        default=None, description="Question ids evaluated, when scope is QUESTIONS"
    )
    student_ids: list[UUID] | None = Field(
        default=None,
        description="Contest team member ids evaluated, when scope is STUDENTS",
    )
    created_at: datetime = Field(..., description="When this run was created (UTC)")
    created_by: UUID = Field(..., description="User who triggered this run")


class EvaluationPreparationDetails(BaseModel):
    """Details prepared for executing a submission evaluation."""

    submission: Submission
    testcases: list[QuestionTestCaseResponse]
    final_source_code: str
    max_score: int
    cpu_time_limit: float = Field(
        default=0.0,
        description="Per-execution CPU time limit (seconds), already capped",
    )
    wall_time_limit: float = Field(
        default=0.0,
        description="Per-execution wall-clock limit (seconds), already capped",
    )
    memory_limit: int = Field(
        default=0, description="Per-execution memory limit (KB), already capped"
    )
    stack_limit: int = Field(default=0, description="Per-execution stack limit (KB)")
    contest_submission_context: ContestSubmissionContext | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)
