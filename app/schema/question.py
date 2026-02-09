from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.utils.enums import QuestionDifficulty


class QuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question_text: str
    difficulty: QuestionDifficulty
    allowed_languages: List[str]
    time_limit_ms: int
    memory_limit_mb: int