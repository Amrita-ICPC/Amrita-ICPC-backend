from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.question import Submission
from app.schema.question import QuestionTestCaseResponse
from app.utils.enums import EvaluationStatus


class EvaluationResponse(BaseModel):
    """Schema for evaluation response."""

    id: UUID = Field(..., description="Evaluation ID")
    contest_id: UUID = Field(..., description="Contest ID")
    is_evaluated: bool = Field(..., description="Whether the evaluation is completed")
    total_submissions: int = Field(..., description="Total submissions to process")
    processed_submissions: int = Field(..., description="Processed submissions count")
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
