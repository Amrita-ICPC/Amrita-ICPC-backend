"""Pydantic schemas for student contest question submissions."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schema.submission import (
    SubmissionDetailLanguageSchema,
    SubmissionDetailQuestionSchema,
    SubmissionDetailUserSchema,
)
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
    status: SubmissionStatus | None = Field(
        None, description="The current status of the submission"
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
    """Payload details for a submission update event.

    ``score``/``passed_testcases``/``total_testcases`` are only known once
    evaluation has produced a terminal verdict, so they're None for the
    "RUNNING" event fired right after submit -- a client relying solely on
    this push channel (rather than re-fetching the submission) needs the
    actual numbers here, not just a status string, or the displayed score
    never changes even though the DB row was updated correctly.
    """

    submission_id: str
    question_id: str
    status: str
    score: int | None = None
    passed_testcases: int | None = None
    total_testcases: int | None = None


class StudentSubmissionUpdateEvent(BaseModel):
    """Schema for SSE submission update events."""

    type: str = "submission_update"
    payload: StudentSubmissionUpdatePayload


class StudentSubmissionDetailResponse(BaseModel):
    """Detailed submission response for student review."""

    submission_id: UUID
    question: SubmissionDetailQuestionSchema
    submitted_by: SubmissionDetailUserSchema
    status: SubmissionStatus | None = None
    score: int
    language: SubmissionDetailLanguageSchema
    submitted_at: datetime
    execution_time_ms: int | None = None
    memory_kb: int | None = None
    passed_testcases: int = 0
    total_testcases: int = 0
    source_code: str

    model_config = ConfigDict(from_attributes=True)
