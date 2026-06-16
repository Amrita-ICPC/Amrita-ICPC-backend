from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    status: str = Field(
        ..., description="Evaluation status (PENDING, RUNNING, COMPLETED)"
    )
    total_submissions: int = Field(..., description="Total submissions to evaluate")
    processed_submissions: int = Field(
        ..., description="Number of evaluated submissions"
    )

    model_config = ConfigDict(from_attributes=True)
