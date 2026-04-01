import dataclasses
from uuid import UUID

from app.utils.enums import QuestionDifficulty


@dataclasses.dataclass
class CreateQuestionData:
    """DTO for creating a new question in the repository layer."""

    question_text: str
    difficulty: QuestionDifficulty
    allowed_languages: list[str]
    testcases: list[dict]
    time_limit_ms: int
    memory_limit_mb: int
    created_by: UUID


@dataclasses.dataclass
class UpdateQuestionData:
    """DTO for updating an existing question in the repository layer."""

    question_text: str | None = None
    difficulty: QuestionDifficulty | None = None
    allowed_languages: list[str] | None = None
    testcases: list[dict] | None = None
    time_limit_ms: int | None = None
    memory_limit_mb: int | None = None
