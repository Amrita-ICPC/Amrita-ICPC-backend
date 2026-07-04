from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    can_create,
    can_delete,
    can_read,
    can_update,
    get_current_user,
    get_current_user_id,
    require_admin,
)
from app.core.clients.database import get_db
from app.core.guards.question import QuestionOperationGuard
from app.core.logger import logger
from app.core.response import create_api_response
from app.core.storage import CodeStorageService
from app.repositories.language import LanguageRepository
from app.repositories.question import QuestionRepository
from app.repositories.tag import TagRepository
from app.schema.base import APIResponse
from app.schema.execution import CodeRunResponse, DraftCodeRunRequest
from app.schema.question import (
    Judge0LanguageResponse,
    PlatformLanguageCreateRequest,
    PlatformLanguageListResponse,
    PlatformLanguageResponse,
    QuestionCreate,
    QuestionResponse,
    QuestionUpdate,
)
from app.schema.tag import TagCreate, TagResponse, TagUpdate
from app.service.code_execution_service import CodeExecutionService
from app.service.question_service import QuestionService
from app.service.tag_service import TagService
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


def get_tag_service(db: AsyncSession = Depends(get_db)) -> TagService:
    """Build TagService with request-scoped dependencies."""
    repository = TagRepository(db)
    return TagService(repository)


def get_code_execution_service(
    db: AsyncSession = Depends(get_db),
) -> CodeExecutionService:
    """Build CodeExecutionService with request-scoped dependencies."""
    return CodeExecutionService(db)


@router.post(
    "/",
    response_model=APIResponse[QuestionResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[can_create("questions")],
)
async def create_question(
    request: Request,
    data: QuestionCreate,
    user_id: UUID = Depends(get_current_user_id),
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
    question = await service.create_question(data, user_id)
    logger.info(f"Question created by user {user_id}: {question.id}")
    return create_api_response(
        request,
        data=question,
        message="Question created successfully",
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    "/languages/judge0",
    response_model=APIResponse[list[Judge0LanguageResponse]],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)],
)
async def get_judge0_languages(
    request: Request,
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
    languages = await service.get_judge0_languages()
    logger.info("Fetched %d Judge0 languages", len(languages))
    return create_api_response(
        request,
        data=languages,
        message="Judge0 languages fetched successfully",
    )


@router.post(
    "/languages/platform",
    response_model=APIResponse[PlatformLanguageResponse],
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
        data=language,
        message="Platform language created successfully",
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    "/languages/platform",
    response_model=APIResponse[PlatformLanguageListResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[],
)
async def get_platform_languages(
    request: Request,
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
    languages = await service.get_platform_languages()
    response = PlatformLanguageListResponse(languages=languages)
    return create_api_response(
        request,
        data=response,
        message="Platform languages fetched successfully",
    )


# --- Tag Routes ---


@router.get(
    "/tags",
    response_model=APIResponse[list[TagResponse]],
    status_code=status.HTTP_200_OK,
    dependencies=[can_read("questions")],
)
async def get_tags(
    request: Request,
    search: str | None = Query(None, description="Search tags by name"),
    service: TagService = Depends(get_tag_service),
):
    """List all tags with optional search."""
    tags = await service.get_tags(search)
    return create_api_response(
        request,
        data=tags,
        message="Tags fetched successfully",
    )


@router.post(
    "/tags",
    response_model=APIResponse[TagResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[can_create("questions")],
)
async def create_tag(
    request: Request,
    data: TagCreate,
    service: TagService = Depends(get_tag_service),
):
    """Create a new tag."""
    tag = await service.create_tag(data)
    logger.info(f"Tag created: {tag.name} ({tag.id})")
    return create_api_response(
        request,
        data=tag,
        message="Tag created successfully",
        status_code=status.HTTP_201_CREATED,
    )


@router.patch(
    "/tags/{tag_id}",
    response_model=APIResponse[TagResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[can_update("questions")],
)
async def update_tag(
    request: Request,
    tag_id: UUID,
    data: TagUpdate,
    service: TagService = Depends(get_tag_service),
):
    """Update an existing tag."""
    tag = await service.update_tag(tag_id, data)
    logger.info(f"Tag updated: {tag_id} -> {tag.name}")
    return create_api_response(
        request,
        data=tag,
        message="Tag updated successfully",
    )


@router.delete(
    "/tags/{tag_id}",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[can_delete("questions")],
)
async def delete_tag(
    request: Request,
    tag_id: UUID,
    service: TagService = Depends(get_tag_service),
):
    """Delete a tag."""
    await service.delete_tag(tag_id)
    logger.info(f"Tag deleted: {tag_id}")
    return create_api_response(
        request,
        data=None,
        message="Tag deleted successfully",
    )


# --- Question ID Routes ---


@router.get(
    "/{question_id}",
    response_model=APIResponse[QuestionResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[can_read("questions")],
)
async def get_question(
    request: Request,
    question_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
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
    question = await service.get_question_by_id(question_id, user_id)
    return create_api_response(
        request,
        data=question,
        message="Question fetched successfully",
    )


@router.patch(
    "/{question_id}",
    response_model=APIResponse[QuestionResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[can_update("questions")],
)
async def update_question(
    request: Request,
    question_id: UUID,
    data: QuestionUpdate,
    user_id: UUID = Depends(get_current_user_id),
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
    question = await service.update_question(question_id, data, user_id)
    logger.info(f"Question updated by user {user_id}: {question_id}")
    return create_api_response(
        request,
        data=question,
        message="Question updated successfully",
    )


@router.delete(
    "/{question_id}",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[can_delete("questions")],
)
async def delete_question(
    request: Request,
    question_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
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
    await service.delete_question(question_id, user_id)
    logger.info(f"Question deleted by user {user_id}: {question_id}")
    return create_api_response(
        request,
        data=None,
        message="Question deleted successfully",
    )


@router.post(
    "/test-draft",
    response_model=APIResponse[CodeRunResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[can_create("questions")],
)
async def test_draft_code(
    request: Request,
    data: DraftCodeRunRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: CodeExecutionService = Depends(get_code_execution_service),
):
    """Run code for a draft question with ad-hoc test cases.

    This endpoint allows testing code snippets before a question is created.
    No data is persisted to the database.

    Args:
        request: FastAPI request object.
        data: Draft code run request with code and test cases.
        user_id: Authenticated user ID.
        service: Injected CodeExecutionService.

    Returns:
        API response containing the execution results.
    """
    result = await service.run_draft_code(data)
    logger.info(f"Draft code execution completed for user {user_id}")
    return create_api_response(
        request,
        data=result,
        message="Code executed successfully",
    )
