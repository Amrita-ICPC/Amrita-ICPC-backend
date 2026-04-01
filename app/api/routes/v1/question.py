from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    can_create,
    can_delete,
    can_read,
    can_update,
    get_current_user,
)
from app.core.clients.database import get_db
from app.core.guards.question import QuestionOperationGuard
from app.core.logger import logger
from app.core.response import create_api_response
from app.repositories.question import QuestionRepository
from app.schema.question import QuestionCreate, QuestionUpdate
from app.service.question_service import QuestionService
from app.service.user_service import UserService
from app.validators.question import QuestionValidator

router = APIRouter()


def get_question_service(db: AsyncSession = Depends(get_db)) -> QuestionService:
    repository = QuestionRepository(db)
    guard = QuestionOperationGuard(db, repository=repository)
    validator = QuestionValidator()
    return QuestionService(repository=repository, guard=guard, validator=validator)


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    dependencies=[can_create("questions")],
)
async def create_question(
    request: Request,
    data: QuestionCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: QuestionService = Depends(get_question_service),
):
    """
    Create a new question.

    Args:
        request: FastAPI request object
        data: QuestionCreate Pydantic model
        current_user: Dictionary holding keycloak JWT claims
        db: Injected database session
        service: Injected QuestionService

    Returns:
        QuestionResponse: The created question details

    Raises:
        InvalidQuestionError: When validation logic fails
    """
    user_id = (await UserService.get_user_by_keycloak_id(db, current_user["sub"])).id
    question = await service.create_question(data, user_id)
    logger.info(f"Question created by user {user_id}: {question.id}")
    return create_api_response(
        request,
        data=question.model_dump(),
        message="Question created successfully",
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    "/{question_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[can_read("questions")],
)
async def get_question(
    request: Request,
    question_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: QuestionService = Depends(get_question_service),
):
    """
    Retrieve a question by ID.

    Args:
        request: FastAPI request object
        question_id: ID of the question
        current_user: Dictionary holding keycloak JWT claims
        db: Injected database session
        service: Injected QuestionService

    Returns:
        QuestionResponse: The queried question details

    Raises:
        QuestionNotFoundError: If the question does not exist
        QuestionPermissionError: If user lacks permission
    """
    user_id = (await UserService.get_user_by_keycloak_id(db, current_user["sub"])).id
    question = await service.get_question_by_id(question_id, user_id)
    return create_api_response(
        request,
        data=question.model_dump(),
        message="Question fetched successfully",
    )


@router.patch(
    "/{question_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[can_update("questions")],
)
async def update_question(
    request: Request,
    question_id: UUID,
    data: QuestionUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: QuestionService = Depends(get_question_service),
):
    """
    Update a question.

    Args:
        request: FastAPI request object
        question_id: ID of the question
        data: QuestionUpdate Pydantic model
        current_user: Dictionary holding keycloak JWT claims
        db: Injected database session
        service: Injected QuestionService

    Returns:
        QuestionResponse: The updated question details

    Raises:
        QuestionNotFoundError: If the question does not exist
        InvalidQuestionError: When validation logic fails
        QuestionPermissionError: If user lacks management permissions
    """
    user_id = (await UserService.get_user_by_keycloak_id(db, current_user["sub"])).id
    question = await service.update_question(question_id, data, user_id)
    logger.info(f"Question updated by user {user_id}: {question_id}")
    return create_api_response(
        request,
        data=question.model_dump(),
        message="Question updated successfully",
    )


@router.delete(
    "/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[can_delete("questions")],
)
async def delete_question(
    request: Request,
    question_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: QuestionService = Depends(get_question_service),
):
    """
    Delete a question by ID.

    Args:
        request: FastAPI request object
        question_id: ID of the question
        current_user: Dictionary holding keycloak JWT claims
        db: Injected database session
        service: Injected QuestionService

    Raises:
        QuestionNotFoundError: If the question does not exist
        QuestionPermissionError: If user lacks management permissions
    """
    user_id = (await UserService.get_user_by_keycloak_id(db, current_user["sub"])).id
    await service.delete_question(question_id, user_id)
    logger.info(f"Question deleted by user {user_id}: {question_id}")
    return create_api_response(
        request,
        message="Question deleted successfully",
    )
