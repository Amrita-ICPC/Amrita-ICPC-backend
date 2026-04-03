import dataclasses
from copy import deepcopy
from typing import TYPE_CHECKING
from uuid import UUID

from app.utils.enums import QuestionDifficulty

if TYPE_CHECKING:
    from app.models.question import Question


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


def clone_question_to_create_data(
    question: "Question", created_by: UUID
) -> CreateQuestionData:
    """Build a create-question DTO from an existing question entity.

    Args:
        question: Source question entity to clone.
        created_by: User ID that should own the cloned question.

    Returns:
        A CreateQuestionData DTO with deep-copied mutable fields.
    """

    return CreateQuestionData(
        question_text=question.question_text,
        difficulty=question.difficulty,
        allowed_languages=deepcopy(question.allowed_languages),
        testcases=deepcopy(question.testcases),
        time_limit_ms=question.time_limit_ms,
        memory_limit_mb=question.memory_limit_mb,
        created_by=created_by,
    )
