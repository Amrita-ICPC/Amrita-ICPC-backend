from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    can_create,
    can_delete,
    can_read,
    can_update,
    get_current_user,
    require_admin,
)
from app.core.clients.database import get_db
from app.core.guards.question import QuestionOperationGuard
from app.core.logger import logger
from app.core.response import create_api_response
from app.core.storage import CodeStorageService
from app.repositories.language import LanguageRepository
from app.repositories.question import QuestionRepository
from app.schema.question import (
    PlatformLanguageCreateRequest,
    PlatformLanguageListResponse,
    QuestionCreate,
    QuestionUpdate,
)
from app.service.question_service import QuestionService
from app.service.user_service import UserService
from app.validators.question import QuestionValidator

router = APIRouter()


def get_question_service(db: AsyncSession = Depends(get_db)) -> QuestionService:
    """Build QuestionService with request-scoped dependencies.

    Args:
        db: Async database session injected by FastAPI.

    Returns:
        Configured QuestionService instance.
    """
    repository = QuestionRepository(db)
    language_repository = LanguageRepository(db)
    guard = QuestionOperationGuard(db, repository=repository)
    validator = QuestionValidator()
    return QuestionService(
        repository=repository,
        language_repository=language_repository,
        guard=guard,
        validator=validator,
        code_storage_service=CodeStorageService(),
    )


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
    """Create a new question.

    Args:
        request: FastAPI request object.
        data: Question creation payload.
        current_user: Authenticated user claims from token.
        db: Async database session.
        service: Injected QuestionService.

    Returns:
        API response containing the created question.

    Raises:
        InvalidQuestionError: If validation fails.
        QuestionPermissionError: If user lacks create permission.
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
    "/languages/judge0",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)],
)
async def get_judge0_languages(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: QuestionService = Depends(get_question_service),
):
    """Fetch available languages from Judge0.

    Args:
        request: FastAPI request object.
        current_user: Authenticated user claims.
        service: Injected QuestionService.

    Returns:
        API response containing normalized Judge0 language list.

    Raises:
        Judge0ServiceError: If Judge0 request fails.
    """
    _ = current_user
    languages = await service.get_judge0_languages()
    logger.info("Fetched %d Judge0 languages", len(languages))
    return create_api_response(
        request,
        data=[language.model_dump() for language in languages],
        message="Judge0 languages fetched successfully",
    )


@router.post(
    "/languages/platform",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_platform_language(
    request: Request,
    payload: PlatformLanguageCreateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: QuestionService = Depends(get_question_service),
):
    """Create a platform language mapping from Judge0.

    Args:
        request: FastAPI request object.
        payload: Mapping request payload.
        current_user: Authenticated admin claims.
        service: Injected QuestionService.

    Returns:
        API response containing created platform language mapping.

    Raises:
        InvalidQuestionError: If mapping is invalid or duplicates existing entries.
        Judge0ServiceError: If Judge0 request fails.
    """
    language = await service.create_platform_language(payload)
    logger.info(
        "Platform language created by admin %s: %s (%s)",
        current_user.get("sub"),
        language.name,
        language.id,
    )
    return create_api_response(
        request,
        data=language.model_dump(),
        message="Platform language created successfully",
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    "/languages/platform",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)],
)
async def get_platform_languages(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: QuestionService = Depends(get_question_service),
):
    """List platform language mappings.

    Args:
        request: FastAPI request object.
        current_user: Authenticated admin claims.
        service: Injected QuestionService.

    Returns:
        API response containing platform language mappings.
    """
    _ = current_user
    languages = await service.get_platform_languages()
    response = PlatformLanguageListResponse(languages=languages)
    return create_api_response(
        request,
        data=response.model_dump(),
        message="Platform languages fetched successfully",
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
    """Retrieve a question by ID.

    Args:
        request: FastAPI request object.
        question_id: Target question ID.
        current_user: Authenticated user claims.
        db: Async database session.
        service: Injected QuestionService.

    Returns:
        API response containing hydrated question details.

    Raises:
        QuestionNotFoundError: If question does not exist.
        QuestionPermissionError: If user lacks read permission.
        CodeStorageError: If template code hydration fails.
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
    """Update a question.

    Args:
        request: FastAPI request object.
        question_id: Target question ID.
        data: Partial update payload.
        current_user: Authenticated user claims.
        db: Async database session.
        service: Injected QuestionService.

    Returns:
        API response containing updated question details.

    Raises:
        QuestionNotFoundError: If question does not exist.
        QuestionPermissionError: If user lacks manage permission.
        InvalidQuestionError: If validation fails.
        CodeStorageError: If template storage update fails.
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
    question_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: QuestionService = Depends(get_question_service),
):
    """Delete a question by ID.

    Args:
        question_id: Target question ID.
        current_user: Authenticated user claims.
        db: Async database session.
        service: Injected QuestionService.

    Returns:
        Empty HTTP 204 response.

    Raises:
        QuestionNotFoundError: If question does not exist.
        QuestionPermissionError: If user lacks manage permission.
    """
    user_id = (await UserService.get_user_by_keycloak_id(db, current_user["sub"])).id
    await service.delete_question(question_id, user_id)
    logger.info(f"Question deleted by user {user_id}: {question_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
