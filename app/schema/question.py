from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import QuestionDifficulty

if TYPE_CHECKING:
    from app.models.question import Question


class QuestionBase(BaseModel):
    question_text: str = Field(..., description="The problem statement and description")
    difficulty: QuestionDifficulty = Field(
        ..., description="Difficulty level of the question"
    )
    time_limit_ms: int = Field(..., gt=0, description="Time limit in milliseconds")
    memory_limit_mb: int = Field(..., gt=0, description="Memory limit in megabytes")


class QuestionTestCaseCreate(BaseModel):
    input: str
    output: str
    is_hidden: bool = True
    weight: int = Field(default=1, ge=1)
    order: int | None = Field(default=None, ge=0)


class QuestionTemplateCreate(BaseModel):
    language_id: int = Field(..., gt=0)
    starter_code: str
    driver_code: str | None = None
    solution_code: str | None = None


class UpdateQuestionTestCaseRequest(BaseModel):
    input: str | None = None
    output: str | None = None
    is_hidden: bool | None = None
    weight: int | None = Field(default=None, ge=1)
    order: int | None = Field(default=None, ge=0)


class UpdateQuestionTemplateRequest(BaseModel):
    language_id: int | None = Field(default=None, gt=0)
    starter_code: str | None = None
    driver_code: str | None = None
    solution_code: str | None = None


class QuestionCreate(QuestionBase):
    allowed_languages: List[int] = Field(
        ..., description="List of allowed platform language IDs"
    )
    tag_ids: List[UUID] = Field(
        default_factory=list, description="List of tag IDs associated with the question"
    )
    testcases: List[QuestionTestCaseCreate] = Field(
        ..., description="List of testcases with input/output and visibility"
    )
    templates: List[QuestionTemplateCreate] = Field(
        default_factory=list,
        description="Starter/driver/solution templates per language",
    )


class QuestionUpdate(BaseModel):
    question_text: Optional[str] = None
    difficulty: Optional[QuestionDifficulty] = None
    allowed_languages: Optional[List[int]] = None
    tag_ids: Optional[List[UUID]] = None
    testcases: Optional[List[QuestionTestCaseCreate]] = None
    templates: Optional[List[QuestionTemplateCreate]] = None
    time_limit_ms: Optional[int] = Field(None, gt=0)
    memory_limit_mb: Optional[int] = Field(None, gt=0)


class AddQuestionTemplatesRequest(BaseModel):
    """Request model for adding multiple templates to an existing question.

    Each template is associated with a language and contains starter code
    plus optional driver and solution code.
    """

    templates: List[QuestionTemplateCreate] = Field(
        ..., description="List of templates to add to the question"
    )


class AddQuestionTestCasesRequest(BaseModel):
    """Request model for adding multiple test cases to an existing question."""

    testcases: List[QuestionTestCaseCreate] = Field(
        ..., description="List of test cases to add to the question"
    )


class RemoveQuestionTestCasesRequest(BaseModel):
    """Request model for removing multiple test cases from an existing question."""

    testcase_ids: List[UUID] = Field(
        ..., description="List of test case IDs to remove from the question"
    )


class RemoveQuestionTemplatesRequest(BaseModel):
    """Request model for removing multiple templates from an existing question."""

    language_ids: List[int] = Field(
        ..., description="List of language IDs whose templates should be removed"
    )


class UpdateQuestionMetadataRequest(BaseModel):
    """Request model for updating question metadata without modifying test cases or templates.

    Allows updating question text, difficulty level, execution limits, allowed languages, and tags.
    All fields are optional for partial updates.
    """

    question_text: Optional[str] = Field(
        None, description="Updated problem statement and description"
    )
    difficulty: Optional[QuestionDifficulty] = Field(
        None, description="Updated difficulty level"
    )
    time_limit_ms: Optional[int] = Field(
        None, gt=0, description="Updated time limit in milliseconds"
    )
    memory_limit_mb: Optional[int] = Field(
        None, gt=0, description="Updated memory limit in megabytes"
    )
    allowed_languages: Optional[List[int]] = Field(
        None, description="Updated list of allowed language IDs"
    )
    tag_ids: Optional[List[UUID]] = Field(None, description="Updated list of tag IDs")


class AddQuestionAllowedLanguagesRequest(BaseModel):
    """Request model for adding allowed languages to an existing question."""

    language_ids: List[int] = Field(
        ...,
        min_length=1,
        description="List of language IDs to add to allowed languages",
    )


class RemoveQuestionAllowedLanguagesRequest(BaseModel):
    """Request model for removing allowed languages from an existing question."""

    language_ids: List[int] = Field(
        ...,
        min_length=1,
        description="List of language IDs to remove from allowed languages",
    )


class UpdateQuestionAllowedLanguagesRequest(BaseModel):
    """Request model for replacing all allowed languages of an existing question."""

    language_ids: List[int] = Field(
        ...,
        min_length=1,
        description="Full replacement list of allowed language IDs",
    )


class QuestionLanguageMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    language_id: int


class QuestionTestCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    input: str
    output: str
    is_hidden: bool
    weight: int
    order: int | None


class QuestionTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    language_id: int
    starter_code: str
    driver_code: str | None
    solution_code: str | None


class QuestionResponse(QuestionBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    testcases: List[QuestionTestCaseResponse] = Field(default_factory=list)
    templates: List[QuestionTemplateResponse] = Field(default_factory=list)
    allowed_languages: List[str] = Field(default_factory=list)
    tag_ids: List[UUID] = Field(default_factory=list)

    @classmethod
    def from_question(cls, question: "Question") -> "QuestionResponse":
        language_names: list[str] = []
        for mapping in getattr(question, "languages", []) or []:
            language = getattr(mapping, "language", None)
            name = getattr(language, "name", None)
            if isinstance(name, str) and name:
                language_names.append(name)

        testcase_items = [
            QuestionTestCaseResponse(
                id=testcase.id,
                input=testcase.input,
                output=testcase.output,
                is_hidden=testcase.is_hidden,
                weight=testcase.weight,
                order=testcase.order,
            )
            for testcase in (getattr(question, "testcases", []) or [])
        ]

        template_items = [
            QuestionTemplateResponse(
                id=template.id,
                language_id=template.language_id,
                starter_code=template.starter_code,
                driver_code=template.driver_code,
                solution_code=template.solution_code,
            )
            for template in (getattr(question, "templates", []) or [])
        ]

        tag_ids = [
            question_tag.tag_id
            for question_tag in (getattr(question, "tags", []) or [])
        ]

        return cls(
            id=question.id,
            question_text=question.question_text,
            difficulty=question.difficulty,
            time_limit_ms=question.time_limit_ms,
            memory_limit_mb=question.memory_limit_mb,
            created_by=question.created_by,
            created_at=question.created_at,
            updated_at=question.updated_at,
            testcases=testcase_items,
            templates=template_items,
            allowed_languages=list(dict.fromkeys(language_names)),
            tag_ids=tag_ids,
        )


class QuestionListSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question_text: str = Field(..., description="The problem statement and description")
    difficulty: QuestionDifficulty = Field(
        ..., description="Difficulty level of the question"
    )
    allowed_languages: List[str] = Field(default_factory=list)
    time_limit_ms: int = Field(..., gt=0, description="Time limit in milliseconds")
    memory_limit_mb: int = Field(..., gt=0, description="Memory limit in megabytes")
    tag_ids: List[UUID] = Field(default_factory=list)
    testcase_count: int = Field(0, description="Number of testcases")
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_question(cls, question: "Question") -> "QuestionListSummaryResponse":
        language_names: list[str] = []
        for mapping in getattr(question, "languages", []) or []:
            language = getattr(mapping, "language", None)
            name = getattr(language, "name", None)
            if isinstance(name, str) and name:
                language_names.append(name)

        testcase_count = getattr(question, "testcase_count", None)
        if testcase_count is None:
            testcase_count = len(getattr(question, "testcases", []) or [])

        tag_ids = [
            question_tag.tag_id
            for question_tag in (getattr(question, "tags", []) or [])
        ]

        return cls(
            id=question.id,
            question_text=question.question_text,
            difficulty=question.difficulty,
            time_limit_ms=question.time_limit_ms,
            memory_limit_mb=question.memory_limit_mb,
            allowed_languages=list(dict.fromkeys(language_names)),
            tag_ids=tag_ids,
            testcase_count=testcase_count,
            created_by=question.created_by,
            created_at=question.created_at,
            updated_at=question.updated_at,
        )


class Judge0LanguageResponse(BaseModel):
    id: int
    name: str


class PlatformLanguageCreateRequest(BaseModel):
    judge0_language_id: int = Field(..., gt=0)
    slug: str | None = None
    file_extension: str | None = None
    monaco_language: str | None = None


class PlatformLanguageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    file_extension: str | None
    monaco_language: str | None


class PlatformLanguageListResponse(BaseModel):
    languages: list[PlatformLanguageResponse]
