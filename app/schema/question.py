from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel

from app.utils.enums import QuestionDifficulty


class QuestionResponse(BaseModel):
    id: UUID
    question_text: str
    difficulty: QuestionDifficulty
    allowed_languages: List[str]
    time_limit_ms: int
    memory_limit_mb: int

    class Config:
        from_attributes = True