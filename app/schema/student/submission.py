"""Pydantic schemas for student contest question submissions."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import SubmissionStatus


class StudentSubmissionRequest(BaseModel):
    """Request schema for submitting code to a contest question."""

    code: str = Field(..., min_length=1, description="Source code to submit")
    language_id: int = Field(
        ...,
        gt=0,
        description="Judge0 language ID (54=Python, 71=Java, 50=C++, etc)",
    )


class StudentSubmissionResponse(BaseModel):
    """Response schema for a contest question submission."""

    id: UUID = Field(..., description="The unique ID of the submission")
    question_id: UUID = Field(..., description="The ID of the question submitted for")
    language_id: int = Field(..., description="Judge0 language ID used")
    status: SubmissionStatus = Field(
        ..., description="The current status of the submission"
    )
    score: int = Field(..., description="Score achieved on this submission")
    passed_testcases: int = Field(..., description="Number of passed test cases")
    total_testcases: int = Field(
        ..., description="Total number of test cases for the question"
    )
    created_at: datetime = Field(
        ..., description="Timestamp when the submission was created"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentSubmissionUpdatePayload(BaseModel):
    """Payload details for a submission update event."""

    submission_id: str
    question_id: str
    status: str


class StudentSubmissionUpdateEvent(BaseModel):
    """Schema for SSE submission update events."""

    type: str = "submission_update"
    payload: StudentSubmissionUpdatePayload
