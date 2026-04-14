"""Mapper functions for contest question data transformations.

This module provides pure mapping functions that transform data between different
layers (API schemas <-> repository DTOs <-> ORM entities). All functions are:
    - Deterministic: Same input always produces same output
    - Pure: No side effects, no database access
    - Unidirectional: Map from source to target format

Mapper functions handle:
    - API schema (Pydantic) to repository DTO conversions
    - Repository DTO to ORM entity conversions
    - ORM entity to API response schema conversions
"""

from uuid import UUID

from app.models.contest import ContestQuestion
from app.repositories.dto.contest_question import AddContestQuestionData
from app.schema.contest import (
    AddContestQuestionRequest,
    ContestQuestionResponse,
)


def build_add_contest_question_dto(
    request: AddContestQuestionRequest,
    contest_id: UUID,
    created_by: UUID,
) -> AddContestQuestionData:
    """
    Map add question request schema to repository DTO.

    Transforms the API request schema into a DTO suitable for repository operations,
    adding context like contest_id and created_by timestamp.

    Args:
        request: The API request containing question_id, order, duration, score.
        contest_id: ID of the contest to add the question to.
        created_by: ID of the user performing the operation.

    Returns:
        AddContestQuestionData: Repository DTO ready for persistence.

    Example:
        >>> request = AddContestQuestionRequest(
        ...     question_id=UUID(...), order=1, duration=300, score=100
        ... )
        >>> dto = build_add_contest_question_dto(request, contest_id, user_id)
        >>> assert dto.contest_id == contest_id
    """
    return AddContestQuestionData(
        contest_id=contest_id,
        question_id=request.question_id,
        order=request.order,
        duration=request.duration,
        score=request.score,
        created_by=created_by,
    )


def to_contest_question_response(
    contest_question: ContestQuestion,
) -> ContestQuestionResponse:
    """
    Map ORM entity to API response schema.

    Transforms a ContestQuestion ORM object into the response schema expected
    by API clients.

    Args:
        contest_question: The ContestQuestion ORM entity.

    Returns:
        ContestQuestionResponse: API response schema with all question metadata.

    Example:
        >>> cq = ContestQuestion(question_id=..., order=1, score=100, ...)
        >>> response = to_contest_question_response(cq)
        >>> assert response.order == 1
    """
    return ContestQuestionResponse.model_validate(contest_question)


def build_contest_question_entity(
    data: AddContestQuestionData,
) -> ContestQuestion:
    """
    Map repository DTO to ORM entity.

    Transforms a repository DTO into a ContestQuestion ORM object ready for
    persistence to the database.

    Args:
        data: The AddContestQuestionData repository DTO.

    Returns:
        ContestQuestion: ORM entity with all fields populated (except database-assigned fields).

    Example:
        >>> data = AddContestQuestionData(
        ...     contest_id=..., question_id=..., order=1, duration=300, score=100, created_by=...
        ... )
        >>> entity = build_contest_question_entity(data)
        >>> assert entity.order == 1
    """
    return ContestQuestion(
        contest_id=data.contest_id,
        question_id=data.question_id,
        order=data.order,
        duration=data.duration,
        score=data.score,
        created_by=data.created_by,
    )
