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


class EvaluationPreparationDetails(BaseModel):
    """Details prepared for executing a submission evaluation."""

    submission: Submission
    testcases: list[QuestionTestCaseResponse]
    final_source_code: str
    max_score: int
    contest_submission_context: ContestSubmissionContext | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)
