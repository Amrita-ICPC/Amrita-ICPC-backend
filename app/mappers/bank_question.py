from typing import TYPE_CHECKING

from app.models.question import QuestionTemplate
from app.schema.question import (
    BankQuestionMetadataResponse,
    QuestionListSummaryResponse,
    QuestionResponse,
    QuestionTemplateCreate,
)
from app.schema.tag import TagResponse


if TYPE_CHECKING:
    from app.models.question import Question


def to_bank_question_metadata_responses(
    questions: list["Question"],
) -> list[BankQuestionMetadataResponse]:
    """Map question ORM list to metadata response schemas."""
    return [
        BankQuestionMetadataResponse(
            id=question.id,
            title=question.title or "Untitled Question",
            difficulty=question.difficulty,
            tags=[
                TagResponse(id=qt.tag.id, name=qt.tag.name)
                for qt in (question.tags or [])
                if qt.tag
            ],
        )
        for question in questions
    ]


def to_bank_question_response(question: "Question") -> QuestionResponse:
    """Map question ORM object to detailed response schema."""
    return QuestionResponse.from_question(question)


def to_bank_question_summary_responses(
    questions: list["Question"],
) -> list[QuestionListSummaryResponse]:
    """Map question ORM list to summary response schemas."""
    return [
        QuestionListSummaryResponse.from_question(question) for question in questions
    ]


def build_template_entities(
    templates: list[QuestionTemplateCreate],
) -> list[QuestionTemplate]:
    """Map template create schemas to ORM entities.

    Args:
        templates: List of template creation requests.

    Returns:
        List of QuestionTemplate ORM objects.
    """
    return [
        QuestionTemplate(
            language_id=template.language_id,
            starter_code=template.starter_code,
            driver_code=template.driver_code,
            solution_code=template.solution_code,
        )
        for template in templates
    ]
