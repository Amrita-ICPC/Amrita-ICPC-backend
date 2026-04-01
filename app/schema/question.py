from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import QuestionDifficulty


class QuestionBase(BaseModel):
    question_text: str = Field(..., description="The problem statement and description")
    difficulty: QuestionDifficulty = Field(
        ..., description="Difficulty level of the question"
    )
    allowed_languages: List[str] = Field(
        ..., description="List of allowed programming languages"
    )
    testcases: List[dict[str, Any]] = Field(
        ..., description="List of testcases with input/output and visibility"
    )
    time_limit_ms: int = Field(..., gt=0, description="Time limit in milliseconds")
    memory_limit_mb: int = Field(..., gt=0, description="Memory limit in megabytes")


class QuestionCreate(QuestionBase):
    pass


class QuestionUpdate(BaseModel):
    question_text: Optional[str] = None
    difficulty: Optional[QuestionDifficulty] = None
    allowed_languages: Optional[List[str]] = None
    testcases: Optional[List[dict[str, Any]]] = None
    time_limit_ms: Optional[int] = Field(None, gt=0)
    memory_limit_mb: Optional[int] = Field(None, gt=0)


class QuestionResponse(QuestionBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime
