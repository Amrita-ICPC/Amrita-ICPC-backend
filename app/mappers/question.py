from uuid import UUID

from app.models.question import Question, QuestionLanguage, QuestionTemplate, TestCase
from app.models.tag import QuestionTag
from app.repositories.dto.question import (
    CreateQuestionData,
    CreateQuestionTemplateData,
    CreateQuestionTestCaseData,
    UpdateQuestionData,
)
from app.schema.question import (
    QuestionCreate,
    QuestionTemplateCreate,
    QuestionTestCaseCreate,
    QuestionUpdate,
    UpdateQuestionMetadataRequest,
)


def build_create_testcase_dtos(
    testcases: list[QuestionTestCaseCreate],
) -> list[CreateQuestionTestCaseData]:
    """Map question testcase payloads to repository DTOs with stable ordering."""
    testcase_dtos: list[CreateQuestionTestCaseData] = []
    for index, testcase in enumerate(testcases):
        testcase_dtos.append(
            CreateQuestionTestCaseData(
                input=testcase.input,
                output=testcase.output,
                is_hidden=testcase.is_hidden,
                weight=testcase.weight,
                order=testcase.order if testcase.order is not None else index,
                is_ordered=testcase.is_ordered,
            )
        )
    return testcase_dtos


def build_update_testcase_dtos(
    testcases: list[QuestionTestCaseCreate] | None,
) -> list[CreateQuestionTestCaseData] | None:
    """Map optional testcase updates to repository DTOs with stable ordering."""
    if testcases is None:
        return None

    testcase_dtos: list[CreateQuestionTestCaseData] = []
    for index, testcase in enumerate(testcases):
        testcase_dtos.append(
            CreateQuestionTestCaseData(
                input=testcase.input,
                output=testcase.output,
                is_hidden=testcase.is_hidden,
                weight=testcase.weight,
                order=testcase.order if testcase.order is not None else index,
                is_ordered=testcase.is_ordered,
            )
        )
    return testcase_dtos


def build_appended_testcase_dtos(
    testcases: list[QuestionTestCaseCreate],
    *,
    starting_order: int,
) -> list[CreateQuestionTestCaseData]:
    """Map testcase payloads to DTOs with an order offset for append operations."""
    testcase_dtos: list[CreateQuestionTestCaseData] = []
    for index, testcase in enumerate(testcases):
        testcase_dtos.append(
            CreateQuestionTestCaseData(
                input=testcase.input,
                output=testcase.output,
                is_hidden=testcase.is_hidden,
                weight=testcase.weight,
                order=starting_order + index,
                is_ordered=testcase.is_ordered,
            )
        )
    return testcase_dtos


def build_testcase_entities(
    testcase_dtos: list[CreateQuestionTestCaseData],
    *,
    created_by: UUID,
) -> list[TestCase]:
    """Map testcase DTOs to ORM entities for persistence."""
    return [
        TestCase(
            input=testcase.input,
            output=testcase.output,
            is_hidden=testcase.is_hidden,
            weight=testcase.weight,
            order=testcase.order,
            is_ordered=testcase.is_ordered,
            created_by=created_by,
        )
        for testcase in testcase_dtos
    ]


def build_template_dto(
    template_id: UUID,
    template: QuestionTemplateCreate,
    solution_code_value: str | None,
) -> CreateQuestionTemplateData:
    """Map a template payload to repository DTO after storage resolution."""
    return CreateQuestionTemplateData(
        id=template_id,
        language_id=template.language_id,
        starter_code=template.starter_code,
        driver_code=template.driver_code,
        solution_code=solution_code_value,
    )


def build_create_question_dto(
    question_data: QuestionCreate,
    *,
    question_id: UUID,
    created_by: UUID,
    testcase_dtos: list[CreateQuestionTestCaseData],
    template_dtos: list[CreateQuestionTemplateData],
) -> CreateQuestionData:
    """Map create-question schema + relation DTOs to repository create DTO."""
    return CreateQuestionData(
        id=question_id,
        title=question_data.title,
        question_text=question_data.question_text,
        difficulty=question_data.difficulty,
        allowed_language_ids=question_data.allowed_languages,
        tag_ids=question_data.tag_ids,
        testcases=testcase_dtos,
        templates=template_dtos,
        time_limit_ms=question_data.time_limit_ms,
        memory_limit_mb=question_data.memory_limit_mb,
        created_by=created_by,
        question_type=question_data.question_type,
    )


def build_update_question_dto(
    update_data: QuestionUpdate,
    *,
    testcase_dtos: list[CreateQuestionTestCaseData] | None,
    template_dtos: list[CreateQuestionTemplateData] | None,
) -> UpdateQuestionData:
    """Map question update schema + relation DTOs to repository update DTO."""
    return UpdateQuestionData(
        title=update_data.title,
        question_text=update_data.question_text,
        difficulty=update_data.difficulty,
        allowed_languages=update_data.allowed_languages,
        tag_ids=update_data.tag_ids,
        testcases=testcase_dtos,
        templates=template_dtos,
        time_limit_ms=update_data.time_limit_ms,
        memory_limit_mb=update_data.memory_limit_mb,
    )


def build_metadata_update_dto(
    metadata: UpdateQuestionMetadataRequest,
) -> UpdateQuestionData:
    """Map question metadata update schema to repository update DTO.

    Converts metadata-only update request to DTO for persistence.
    Testcases and templates are not modified by this mapper.

    Args:
        metadata: Metadata update request containing optional question fields.

    Returns:
        UpdateQuestionData DTO with metadata fields populated.
    """
    return UpdateQuestionData(
        title=metadata.title,
        question_text=metadata.question_text,
        difficulty=metadata.difficulty,
        allowed_languages=metadata.allowed_languages,
        tag_ids=metadata.tag_ids,
        time_limit_ms=metadata.time_limit_ms,
        memory_limit_mb=metadata.memory_limit_mb,
        testcases=None,
        templates=None,
    )


def build_question_entity(data: CreateQuestionData) -> Question:
    """Map question create DTO to ORM entity graph."""
    return Question(
        id=data.id,
        title=data.title,
        question_text=data.question_text,
        difficulty=data.difficulty,
        question_type=data.question_type,
        time_limit_ms=data.time_limit_ms,
        memory_limit_mb=data.memory_limit_mb,
        created_by=data.created_by,
        languages=[
            QuestionLanguage(question_id=data.id, language_id=language_id)
            for language_id in data.allowed_language_ids
        ],
        tags=[QuestionTag(tag_id=tag_id) for tag_id in data.tag_ids],
        testcases=[
            TestCase(
                input=testcase.input,
                output=testcase.output,
                is_hidden=testcase.is_hidden,
                weight=testcase.weight,
                order=testcase.order,
                is_ordered=testcase.is_ordered,
                created_by=data.created_by,
            )
            for testcase in data.testcases
        ],
        templates=[
            QuestionTemplate(
                id=template.id,
                language_id=template.language_id,
                starter_code=template.starter_code,
                driver_code=template.driver_code,
                solution_code=template.solution_code,
            )
            for template in data.templates
        ],
    )


def apply_question_updates(question: Question, update_data: UpdateQuestionData) -> None:
    """Apply update DTO values onto a question ORM entity."""
    update_dict = update_data.__dict__
    for field, value in update_dict.items():
        if value is None:
            continue
        if field == "allowed_languages":
            question.languages = [
                QuestionLanguage(question_id=question.id, language_id=language_id)
                for language_id in value
            ]
            continue
        if field == "tag_ids":
            question.tags = [QuestionTag(tag_id=tag_id) for tag_id in value]
            continue
        if field == "testcases":
            continue
        if field == "templates":
            continue
        setattr(question, field, value)
