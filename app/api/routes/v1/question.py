from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    can_create,
    can_delete,
    can_read,
    can_update,
    get_current_user_id,
)
from app.core.clients.database import get_db
from app.core.guards.question import QuestionOperationGuard
from app.core.logger import logger
from app.repositories.question import QuestionRepository
from app.schema.question import QuestionCreate, QuestionResponse, QuestionUpdate
from app.service.question_service import QuestionService
from app.validators.question import QuestionValidator

router = APIRouter()


def get_question_service(db: AsyncSession = Depends(get_db)) -> QuestionService:
    repository = QuestionRepository(db)
    guard = QuestionOperationGuard(db, repository=repository)
    validator = QuestionValidator()
    return QuestionService(repository=repository, guard=guard, validator=validator)


@router.post(
    "/",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[can_create("questions")],
)
async def create_question(
    data: QuestionCreate,
    user_id: UUID = Depends(get_current_user_id),
    service: QuestionService = Depends(get_question_service),
):
    """
    Create a new question.

    Args:
        data: QuestionCreate Pydantic model
        user_id: ID of the currently authenticated user
        service: Injected QuestionService

    Returns:
        QuestionResponse: The created question details

    Raises:
        InvalidQuestionError: When validation logic fails
    """
    question = await service.create_question(data, user_id)
    logger.info(f"Question created by user {user_id}: {question.id}")
    return question


@router.get(
    "/{question_id}",
    response_model=QuestionResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[can_read("questions")],
)
async def get_question(
    question_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: QuestionService = Depends(get_question_service),
):
    """
    Retrieve a question by ID.

    Args:
        question_id: ID of the question
        user_id: ID of the currently authenticated user
        service: Injected QuestionService

    Returns:
        QuestionResponse: The queried question details

    Raises:
        QuestionNotFoundError: If the question does not exist
        QuestionPermissionError: If user lacks permission
    """
    return await service.get_question_by_id(question_id, user_id)


@router.patch(
    "/{question_id}",
    response_model=QuestionResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[can_update("questions")],
)
async def update_question(
    question_id: UUID,
    data: QuestionUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: QuestionService = Depends(get_question_service),
):
    """
    Update a question.

    Args:
        question_id: ID of the question
        data: QuestionUpdate Pydantic model
        user_id: ID of the currently authenticated user
        service: Injected QuestionService

    Returns:
        QuestionResponse: The updated question details

    Raises:
        QuestionNotFoundError: If the question does not exist
        InvalidQuestionError: When validation logic fails
        QuestionPermissionError: If user lacks management permissions
    """
    question = await service.update_question(question_id, data, user_id)
    logger.info(f"Question updated by user {user_id}: {question_id}")
    return question


@router.delete(
    "/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[can_delete("questions")],
)
async def delete_question(
    question_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: QuestionService = Depends(get_question_service),
):
    """
    Delete a question by ID.

    Args:
        question_id: ID of the question
        user_id: ID of the currently authenticated user
        service: Injected QuestionService

    Raises:
        QuestionNotFoundError: If the question does not exist
        QuestionPermissionError: If user lacks management permissions
    """
    await service.delete_question(question_id, user_id)
    logger.info(f"Question deleted by user {user_id}: {question_id}")
