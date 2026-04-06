from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.utils.enums import QuestionDifficulty


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

    languages: List[QuestionLanguageMappingResponse] = Field(default_factory=list)
    testcases: List[QuestionTestCaseResponse] = Field(default_factory=list)
    templates: List[QuestionTemplateResponse] = Field(default_factory=list)
    allowed_languages: List[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def populate_allowed_languages(self) -> "QuestionResponse":
        if not self.allowed_languages and self.languages:
            self.allowed_languages = [item.language_id for item in self.languages]
        return self


class QuestionListSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question_text: str = Field(..., description="The problem statement and description")
    difficulty: QuestionDifficulty = Field(
        ..., description="Difficulty level of the question"
    )
    allowed_languages: List[int] = Field(default_factory=list)
    time_limit_ms: int = Field(..., gt=0, description="Time limit in milliseconds")
    memory_limit_mb: int = Field(..., gt=0, description="Memory limit in megabytes")
    languages: List[QuestionLanguageMappingResponse] = Field(
        default_factory=list, exclude=True
    )
    testcases: List[QuestionTestCaseResponse] = Field(
        default_factory=list, exclude=True
    )
    testcase_count: int = Field(0, description="Number of testcases")
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def compute_count(self) -> "QuestionListSummaryResponse":
        if not self.allowed_languages and self.languages:
            self.allowed_languages = [item.language_id for item in self.languages]
        self.testcase_count = len(self.testcases) if self.testcases else 0
        return self


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
