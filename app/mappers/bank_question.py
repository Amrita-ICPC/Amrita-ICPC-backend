from typing import TYPE_CHECKING

from app.schema.question import QuestionListSummaryResponse, QuestionResponse

if TYPE_CHECKING:
    from app.models.question import Question


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
