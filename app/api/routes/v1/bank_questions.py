from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import can_read, can_update, get_current_user_id
from app.core.clients.database import get_db
from app.core.logger import logger
from app.core.response import create_api_response
from app.core.storage import CodeStorageService
from app.repositories.bank import BankRepository
from app.repositories.language import LanguageRepository
from app.repositories.question import QuestionRepository
from app.schema.bank import (
    BankQuestionBulk,
    BankQuestionCloneRequest,
    BankQuestionFilters,
)
from app.schema.base import PaginationResponse
from app.schema.question import (
    QuestionUpdate,
)
from app.service.bank_question_service import BankQuestionService
from app.utils.enums import BankQuestionSortBy, QuestionDifficulty, SortOrder
from app.validators.bank import BankValidator

router = APIRouter()


def get_bank_question_service(
    db: AsyncSession = Depends(get_db),
) -> BankQuestionService:
    """Build BankQuestionService with request-scoped dependencies.

    Args:
        db: Async database session injected by FastAPI.

    Returns:
        Configured BankQuestionService instance.
    """
    repository = BankRepository(db)
    question_repo = QuestionRepository(db)
    language_repo = LanguageRepository(db)
    validator = BankValidator()
    return BankQuestionService(
        repository=repository,
        question_repo=question_repo,
        validator=validator,
        code_storage_service=CodeStorageService(),
        language_repo=language_repo,
    )


@router.post(
    "/{bank_id}/questions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[can_update("banks")],
)
async def add_questions_to_bank(
    request: Request,
    bank_id: UUID,
    payload: BankQuestionBulk,
    user_id: UUID = Depends(get_current_user_id),
    service: BankQuestionService = Depends(get_bank_question_service),
):
    """Link existing questions to a bank.

    Args:
        request: FastAPI request object.
        bank_id: Target bank ID.
        payload: Bulk question ID payload.
        user_id: Authenticated user ID.
        service: Injected BankQuestionService.

    Returns:
        Success API response.

    Raises:
        BankNotFoundError: If bank does not exist.
        BankAccessDeniedError: If user lacks edit permission.
        QuestionNotFoundError: If any question does not exist.
        BankQuestionAlreadyExistsError: If any association already exists.
    """
    await service.add_questions_to_bank(bank_id, payload.question_ids, user_id)
    logger.info(f"Questions added to bank {bank_id} by user {user_id}")
    return create_api_response(
        request,
        message="Questions added to bank successfully",
        status_code=status.HTTP_201_CREATED,
    )


@router.delete(
    "/{bank_id}/questions",
    status_code=status.HTTP_200_OK,
    dependencies=[can_update("banks")],
)
async def remove_questions_from_bank(
    request: Request,
    bank_id: UUID,
    payload: BankQuestionBulk,
    user_id: UUID = Depends(get_current_user_id),
    service: BankQuestionService = Depends(get_bank_question_service),
):
    """Unlink questions from a bank.

    Args:
        request: FastAPI request object.
        bank_id: Target bank ID.
        payload: Bulk question ID payload.
        user_id: Authenticated user ID.
        service: Injected BankQuestionService.

    Returns:
        Success API response.

    Raises:
        BankNotFoundError: If bank does not exist.
        BankAccessDeniedError: If user lacks edit permission.
        BankQuestionNotFoundError: If any association does not exist.
    """
    await service.remove_questions_from_bank(bank_id, payload.question_ids, user_id)
    logger.info(f"Questions removed from bank {bank_id} by user {user_id}")
    return create_api_response(
        request, message="Questions removed from bank successfully"
    )


@router.post(
    "/{source_bank_id}/questions/clone",
    status_code=status.HTTP_201_CREATED,
    dependencies=[can_update("banks"), can_read("banks")],
)
async def clone_questions_between_banks(
    request: Request,
    source_bank_id: UUID,
    payload: BankQuestionCloneRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: BankQuestionService = Depends(get_bank_question_service),
):
    """Clone questions from one bank to another bank.

    Args:
        request: FastAPI request object.
        source_bank_id: Source bank ID.
        payload: Clone configuration (target bank, copy_all, optional question_ids).
        user_id: Authenticated user ID.
        service: Injected BankQuestionService.

    Returns:
        Success API response with count of cloned questions.

    Raises:
        BankNotFoundError: If source or target bank does not exist.
        BankAccessDeniedError: If user lacks source read or target edit permission.
        BankValidationError: If request payload is invalid.
        BankQuestionNotFoundError: If selected questions are not in source bank.
    """
    cloned_count = await service.clone_questions_between_banks(
        source_bank_id,
        payload.target_bank_id,
        user_id,
        copy_all=payload.copy_all,
        question_ids=payload.question_ids,
    )
    logger.info(
        f"Cloned {cloned_count} questions from bank {source_bank_id} to {payload.target_bank_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data={"cloned_count": cloned_count},
        message="Questions cloned between banks successfully",
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    "/{bank_id}/questions",
    status_code=status.HTTP_200_OK,
    dependencies=[can_read("banks")],
)
async def get_bank_questions(
    request: Request,
    bank_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    title: str | None = Query(None, description="Filter by question title"),
    difficulty: QuestionDifficulty | None = Query(
        None, description="Filter by difficulty"
    ),
    tag: str | None = Query(None, description="Filter by tag name"),
    sort_by: BankQuestionSortBy = Query(
        BankQuestionSortBy.NAME, description="Sort by field"
    ),
    sort_order: SortOrder = Query(SortOrder.ASC, description="Sort order"),
    user_id: UUID = Depends(get_current_user_id),
    service: BankQuestionService = Depends(get_bank_question_service),
):
    """List paginated question summaries linked to a bank.

    Args:
        request: FastAPI request object.
        bank_id: Target bank ID.
        skip: Pagination offset.
        limit: Pagination page size.
        user_id: Authenticated user ID.
        service: Injected BankQuestionService.

    Returns:
        API response with items and pagination metadata.

    Raises:
        BankNotFoundError: If bank does not exist.
        BankAccessDeniedError: If user lacks read permission.
    """
    filters = BankQuestionFilters(
        title=title,
        difficulty=difficulty,
        tag=tag,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total, questions = await service.get_bank_questions(
        bank_id, user_id, skip, limit, filters
    )

    # Exposing the list array via standard JSON serialization using proper API response
    result_list = [q.model_dump() for q in questions]
    total_pages = (total + limit - 1) // limit if limit > 0 else 1
    page = (skip // limit) + 1 if limit > 0 else 1

    return create_api_response(
        request,
        data={"total": total, "items": result_list},
        message="Bank questions fetched successfully",
        pagination=PaginationResponse(
            total=total,
            page=page,
            page_size=limit,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )


@router.get(
    "/{bank_id}/questions/{question_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[can_read("banks")],
)
async def get_bank_question(
    request: Request,
    bank_id: UUID,
    question_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: BankQuestionService = Depends(get_bank_question_service),
):
    """Get a hydrated question detail response within a bank scope.

    Args:
        request: FastAPI request object.
        bank_id: Target bank ID.
        question_id: Target question ID.
        user_id: Authenticated user ID.
        service: Injected BankQuestionService.

    Returns:
        API response containing hydrated question details.

    Raises:
        BankNotFoundError: If bank does not exist.
        BankAccessDeniedError: If user lacks read permission.
        BankQuestionNotFoundError: If question is not linked to the bank.
        QuestionNotFoundError: If question does not exist.
        CodeStorageError: If template code hydration fails.
    """
    question = await service.get_bank_question(bank_id, question_id, user_id)
    return create_api_response(
        request,
        data=question.model_dump(),
        message="Bank question fetched successfully",
    )


@router.put(
    "/{bank_id}/questions/{question_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[can_update("banks")],
)
async def update_bank_question(
    request: Request,
    bank_id: UUID,
    question_id: UUID,
    payload: QuestionUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: BankQuestionService = Depends(get_bank_question_service),
):
    """Perform a comprehensive update of a bank question in a single call.

    Handles metadata, execution limits, tags, allowed languages, code templates,
    and test cases. Test cases and templates provided in the payload will
    REPLACE the existing ones for that question.

    Args:
        request: FastAPI request object.
        bank_id: Target bank ID.
        question_id: Target question ID.
        payload: Full update payload.
        user_id: Authenticated user ID.
        service: Injected BankQuestionService.

    Returns:
        API response containing the fully updated question.

    Raises:
        BankNotFoundError: If the bank does not exist.
        BankAccessDeniedError: If user lacks edit permission for the bank.
        BankQuestionNotFoundError: If the question is not linked to the bank.
        InvalidQuestionError: If any part of the payload fails validation.
    """
    question = await service.update_bank_question(
        bank_id, question_id, payload, user_id
    )
    logger.info(f"Updated question {question_id} in bank {bank_id} by user {user_id}")
    return create_api_response(
        request,
        data=question.model_dump(),
        message="Bank question updated successfully",
    )
