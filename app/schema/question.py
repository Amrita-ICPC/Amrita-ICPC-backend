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


class QuestionLanguageMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    language_id: int


class QuestionTestCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    input: str
    output: str
    is_hidden: bool
    weight: int
    order: int


class QuestionTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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

        if not language_names:
            for template in getattr(question, "templates", []) or []:
                language = getattr(template, "language", None)
                name = getattr(language, "name", None)
                if isinstance(name, str) and name:
                    language_names.append(name)

        testcase_items = [
            QuestionTestCaseResponse(
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
    testcases: List[QuestionTestCaseResponse] = Field(default_factory=list)
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

        if not language_names:
            for template in getattr(question, "templates", []) or []:
                language = getattr(template, "language", None)
                name = getattr(language, "name", None)
                if isinstance(name, str) and name:
                    language_names.append(name)

        testcase_items = [
            QuestionTestCaseResponse(
                input=testcase.input,
                output=testcase.output,
                is_hidden=testcase.is_hidden,
                weight=testcase.weight,
                order=testcase.order,
            )
            for testcase in (getattr(question, "testcases", []) or [])
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
            allowed_languages=list(dict.fromkeys(language_names)),
            testcases=testcase_items,
            tag_ids=tag_ids,
            testcase_count=len(testcase_items),
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
