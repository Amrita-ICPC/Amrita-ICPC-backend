import uuid
from copy import deepcopy
from dataclasses import dataclass
from uuid import UUID

from app.models.question import Question, QuestionLanguage, QuestionTemplate, TestCase
from app.models.tag import QuestionTag


@dataclass(frozen=True)
class TestCaseSnapshot:
    input: str
    output: str
    is_hidden: bool
    weight: int
    order: int


@dataclass(frozen=True)
class TemplateSnapshot:
    language_id: int
    starter_code: str
    driver_code: str | None
    solution_code: str | None


def deep_copy_question_for_clone(
    source_question: Question, created_by: UUID
) -> Question:
    """Clone a question aggregate with fresh identifiers and copied relations."""
    cloned_question_id = uuid.uuid4()
    language_ids: list[int] = deepcopy(
        [language_mapping.language_id for language_mapping in source_question.languages]
    )
    tag_ids: list[UUID] = deepcopy(
        [tag_mapping.tag_id for tag_mapping in source_question.tags]
    )
    testcase_snapshots: list[TestCaseSnapshot] = deepcopy(
        [
            TestCaseSnapshot(
                input=testcase.input,
                output=testcase.output,
                is_hidden=testcase.is_hidden,
                weight=testcase.weight,
                order=testcase.order,
            )
            for testcase in source_question.testcases
        ]
    )
    template_snapshots: list[TemplateSnapshot] = deepcopy(
        [
            TemplateSnapshot(
                language_id=template.language_id,
                starter_code=template.starter_code,
                driver_code=template.driver_code,
                solution_code=template.solution_code,
            )
            for template in source_question.templates
        ]
    )

    return Question(
        id=cloned_question_id,
        question_text=source_question.question_text,
        difficulty=source_question.difficulty,
        time_limit_ms=source_question.time_limit_ms,
        memory_limit_mb=source_question.memory_limit_mb,
        created_by=created_by,
        languages=[
            QuestionLanguage(language_id=language_id, question_id=cloned_question_id)
            for language_id in language_ids
        ],
        tags=[
            QuestionTag(question_id=cloned_question_id, tag_id=tag_id)
            for tag_id in tag_ids
        ],
        testcases=[
            TestCase(
                input=testcase.input,
                question_id=cloned_question_id,
                output=testcase.output,
                is_hidden=testcase.is_hidden,
                weight=testcase.weight,
                order=testcase.order,
                created_by=created_by,
            )
            for testcase in testcase_snapshots
        ],
        templates=[
            QuestionTemplate(
                id=uuid.uuid4(),
                question_id=cloned_question_id,
                language_id=template.language_id,
                starter_code=template.starter_code,
                driver_code=template.driver_code,
                solution_code=template.solution_code,
            )
            for template in template_snapshots
        ],
    )
