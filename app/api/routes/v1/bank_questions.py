from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import can_read, can_update, get_current_user_id
from app.core.clients.database import get_db
from app.core.logger import logger
from app.core.response import create_api_response
from app.core.storage import CodeStorageService
from app.repositories.bank import BankRepository
from app.repositories.question import QuestionRepository
from app.schema.bank import BankQuestionBulk, BankQuestionCloneRequest
from app.schema.base import PaginationResponse
from app.schema.question import (
    AddQuestionTemplatesRequest,
    AddQuestionTestCasesRequest,
    RemoveQuestionTemplatesRequest,
    RemoveQuestionTestCasesRequest,
    UpdateQuestionMetadataRequest,
)
from app.service.bank_question_service import BankQuestionService
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
    validator = BankValidator()
    return BankQuestionService(
        repository=repository,
        question_repo=question_repo,
        validator=validator,
        code_storage_service=CodeStorageService(),
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
    "/{bank_id}/questions/{question_id}/testcases",
    status_code=status.HTTP_201_CREATED,
    dependencies=[can_update("banks")],
)
async def add_testcases_to_question(
    request: Request,
    bank_id: UUID,
    question_id: UUID,
    payload: AddQuestionTestCasesRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: BankQuestionService = Depends(get_bank_question_service),
):
    """Append multiple test cases to a question in a bank.

    Args:
        request: FastAPI request object.
        bank_id: Target bank ID.
        question_id: Target question ID.
        payload: Request body containing test cases to add.
        user_id: Authenticated user ID.
        service: Injected BankQuestionService.

    Returns:
        API response containing the updated question.

    Raises:
        BankNotFoundError: If the bank does not exist.
        BankAccessDeniedError: If user lacks edit permission for the bank.
        BankQuestionNotFoundError: If the question is not linked to the bank.
        InvalidQuestionError: If testcase payload is invalid.
    """
    question = await service.add_testcases_to_question(
        bank_id, question_id, payload, user_id
    )
    logger.info(
        f"Added {len(payload.testcases)} testcases to question {question_id} in bank {bank_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=question.model_dump(),
        message="Test cases added successfully",
        status_code=status.HTTP_201_CREATED,
    )


@router.delete(
    "/{bank_id}/questions/{question_id}/testcases",
    status_code=status.HTTP_200_OK,
    dependencies=[can_update("banks")],
)
async def remove_testcases_from_question(
    request: Request,
    bank_id: UUID,
    question_id: UUID,
    payload: RemoveQuestionTestCasesRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: BankQuestionService = Depends(get_bank_question_service),
):
    """Remove multiple test cases from a question in a bank.

    Args:
        request: FastAPI request object.
        bank_id: Target bank ID.
        question_id: Target question ID.
        payload: Request body containing testcase IDs to remove.
        user_id: Authenticated user ID.
        service: Injected BankQuestionService.

    Returns:
        API response containing the updated question.

    Raises:
        BankNotFoundError: If the bank does not exist.
        BankAccessDeniedError: If user lacks edit permission for the bank.
        BankQuestionNotFoundError: If the question is not linked to the bank.
        InvalidQuestionError: If testcase IDs are invalid.
    """
    question = await service.remove_testcases_from_question(
        bank_id, question_id, payload, user_id
    )
    logger.info(
        f"Removed {len(payload.testcase_ids)} testcases from question {question_id} in bank {bank_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=question.model_dump(),
        message="Test cases removed successfully",
    )


@router.put(
    "/{bank_id}/questions/{question_id}/testcases",
    status_code=status.HTTP_200_OK,
    dependencies=[can_update("banks")],
)
async def update_testcases_of_question(
    request: Request,
    bank_id: UUID,
    question_id: UUID,
    payload: AddQuestionTestCasesRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: BankQuestionService = Depends(get_bank_question_service),
):
    """Replace all test cases of a question in a bank.

    Args:
        request: FastAPI request object.
        bank_id: Target bank ID.
        question_id: Target question ID.
        payload: Request body containing replacement testcases.
        user_id: Authenticated user ID.
        service: Injected BankQuestionService.

    Returns:
        API response containing the updated question.

    Raises:
        BankNotFoundError: If the bank does not exist.
        BankAccessDeniedError: If user lacks edit permission for the bank.
        BankQuestionNotFoundError: If the question is not linked to the bank.
        InvalidQuestionError: If testcase payload is invalid.
    """
    question = await service.update_testcases_of_question(
        bank_id, question_id, payload, user_id
    )
    logger.info(
        f"Updated all testcases for question {question_id} in bank {bank_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=question.model_dump(),
        message="Test cases updated successfully",
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
    total, questions = await service.get_bank_questions(bank_id, user_id, skip, limit)

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


@router.post(
    "/{bank_id}/questions/{question_id}/templates",
    status_code=status.HTTP_201_CREATED,
    dependencies=[can_update("banks")],
)
async def add_templates_to_question(
    request: Request,
    bank_id: UUID,
    question_id: UUID,
    payload: AddQuestionTemplatesRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: BankQuestionService = Depends(get_bank_question_service),
):
    """Add multiple templates to an existing question in a bank.

    This endpoint allows adding code templates (starter, driver, and solution code)
    for multiple languages to an already existing question. It validates that:
    - The question exists and is associated with the bank
    - The user has update permission for the bank
    - Template language IDs are unique within the request
    - No template already exists for each specified language

    Args:
        request: FastAPI request object.
        bank_id: ID of the bank containing the question.
        question_id: ID of the question to add templates to.
        payload: Request body containing list of templates to add.
        user_id: Authenticated user ID performing the operation.
        service: Injected BankQuestionService instance.

    Returns:
        API response with success message indicating templates were added.

    Raises:
        BankNotFoundError: If the bank does not exist.
        BankAccessDeniedError: If the user lacks update permission for the bank.
        BankQuestionNotFoundError: If the question is not linked to the bank.
        QuestionNotFoundError: If the question does not exist.
        QuestionPermissionError: If the user lacks permission to modify the question.
        BankValidationError: If template language IDs are not unique in the request.
        TemplateAlreadyExistsError: If a template already exists for any language.
    """
    await service.add_templates_to_question(bank_id, question_id, payload, user_id)
    logger.info(
        f"Added {len(payload.templates)} templates to question {question_id} in bank {bank_id} by user {user_id}"
    )
    return create_api_response(
        request,
        message="Templates added to question successfully",
        status_code=status.HTTP_201_CREATED,
    )


@router.delete(
    "/{bank_id}/questions/{question_id}/templates",
    status_code=status.HTTP_200_OK,
    dependencies=[can_update("banks")],
)
async def remove_templates_from_question(
    request: Request,
    bank_id: UUID,
    question_id: UUID,
    payload: RemoveQuestionTemplatesRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: BankQuestionService = Depends(get_bank_question_service),
):
    """Remove multiple templates from a question in a bank.

    Args:
        request: FastAPI request object.
        bank_id: Target bank ID.
        question_id: Target question ID.
        payload: Request body containing language IDs to remove.
        user_id: Authenticated user ID.
        service: Injected BankQuestionService.

    Returns:
        API response containing the updated question.

    Raises:
        BankNotFoundError: If the bank does not exist.
        BankAccessDeniedError: If user lacks edit permission for the bank.
        BankQuestionNotFoundError: If the question is not linked to the bank.
        InvalidQuestionError: If language IDs are invalid.
    """
    question = await service.remove_templates_from_question(
        bank_id, question_id, payload, user_id
    )
    logger.info(
        f"Removed {len(payload.language_ids)} templates from question {question_id} in bank {bank_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=question.model_dump(),
        message="Templates removed successfully",
    )


@router.put(
    "/{bank_id}/questions/{question_id}/templates",
    status_code=status.HTTP_200_OK,
    dependencies=[can_update("banks")],
)
async def update_templates_of_question(
    request: Request,
    bank_id: UUID,
    question_id: UUID,
    payload: AddQuestionTemplatesRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: BankQuestionService = Depends(get_bank_question_service),
):
    """Replace all templates of a question in a bank.

    Args:
        request: FastAPI request object.
        bank_id: Target bank ID.
        question_id: Target question ID.
        payload: Request body containing replacement templates.
        user_id: Authenticated user ID.
        service: Injected BankQuestionService.

    Returns:
        API response containing the updated question.

    Raises:
        BankNotFoundError: If the bank does not exist.
        BankAccessDeniedError: If user lacks edit permission for the bank.
        BankQuestionNotFoundError: If the question is not linked to the bank.
        InvalidQuestionError: If template language IDs are invalid.
    """
    question = await service.update_templates_of_question(
        bank_id, question_id, payload, user_id
    )
    logger.info(
        f"Updated all templates for question {question_id} in bank {bank_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=question.model_dump(),
        message="Templates updated successfully",
    )


@router.patch(
    "/{bank_id}/questions/{question_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[can_update("banks")],
)
async def update_question_metadata(
    request: Request,
    bank_id: UUID,
    question_id: UUID,
    payload: UpdateQuestionMetadataRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: BankQuestionService = Depends(get_bank_question_service),
):
    """Update question metadata (text, difficulty, limits, languages, tags) in a bank.

    Allows updating question metadata fields without modifying testcases or templates.
    All fields are optional for partial updates. At least one field must be provided.

    Args:
        request: FastAPI request object.
        bank_id: Target bank ID.
        question_id: Target question ID.
        payload: Request body containing metadata fields to update.
        user_id: Authenticated user ID.
        service: Injected BankQuestionService.

    Returns:
        API response containing the updated question with new metadata.

    Raises:
        BankNotFoundError: If the bank does not exist.
        BankAccessDeniedError: If user lacks edit permission for the bank.
        BankQuestionNotFoundError: If the question is not linked to the bank.
        QuestionNotFoundError: If the question does not exist.
        InvalidQuestionError: If metadata validation fails or no fields provided.
    """
    question = await service.update_question_metadata(
        bank_id, question_id, payload, user_id
    )
    logger.info(
        f"Updated metadata for question {question_id} in bank {bank_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=question.model_dump(),
        message="Question metadata updated successfully",
    )
