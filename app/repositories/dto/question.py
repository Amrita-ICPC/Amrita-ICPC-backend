import dataclasses
from uuid import UUID

from app.utils.enums import QuestionDifficulty


@dataclasses.dataclass
class CreateQuestionTestCaseData:
    """Repository DTO for creating a testcase entity.

    This DTO is used by service layer orchestration to transfer validated
    testcase inputs into repository operations without exposing schema objects.
    """

    input: str
    output: str
    is_hidden: bool
    weight: int
    order: int


@dataclasses.dataclass
class CreateQuestionTemplateData:
    """Repository DTO for creating a template entity.

    Carries language mapping and code payload references (raw code or object key)
    used to persist question template rows.
    """

    id: UUID
    language_id: int
    starter_code: str
    driver_code: str | None
    solution_code: str | None


@dataclasses.dataclass
class CreateQuestionData:
    """DTO for creating a question aggregate in the repository layer.

    Includes scalar question fields plus relation payloads for languages,
    testcases, and templates.
    """

    id: UUID
    question_text: str
    difficulty: QuestionDifficulty
    allowed_language_ids: list[int]
    tag_ids: list[UUID]
    testcases: list[CreateQuestionTestCaseData]
    templates: list[CreateQuestionTemplateData]
    time_limit_ms: int
    memory_limit_mb: int
    created_by: UUID


@dataclasses.dataclass
class UpdateQuestionData:
    """DTO for partial question updates in the repository layer.

    Any field set to None is treated as unchanged by repository logic.
    Relation collections replace existing rows when provided.
    """

    question_text: str | None = None
    difficulty: QuestionDifficulty | None = None
    allowed_languages: list[int] | None = None
    tag_ids: list[UUID] | None = None
    testcases: list[CreateQuestionTestCaseData] | None = None
    templates: list[CreateQuestionTemplateData] | None = None
    time_limit_ms: int | None = None
    memory_limit_mb: int | None = None
