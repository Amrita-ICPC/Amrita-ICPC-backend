from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import can_read, can_update, get_current_user_id
from app.core.clients.database import get_db
from app.core.response import create_api_response
from app.repositories.bank import BankRepository
from app.repositories.question import QuestionRepository
from app.schema.bank import BankQuestionBulk
from app.schema.base import PaginationResponse
from app.service.bank_question_service import BankQuestionService
from app.validators.bank import BankValidator

router = APIRouter()


def get_bank_question_service(
    db: AsyncSession = Depends(get_db),
) -> BankQuestionService:
    repository = BankRepository(db)
    question_repo = QuestionRepository(db)
    validator = BankValidator()
    return BankQuestionService(
        repository=repository, question_repo=question_repo, validator=validator
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
    """Link multiple existing questions to a bank.

    Validates ownership or edit permissions before dynamically mapping a batch
    of distinct questions natively into the target bank's domain.

    Args:
        request: The FastAPI execution request context.
        bank_id: Primary UUID targeting the active Bank.
        payload: The JSON representation containing target associative array values.
        user_id: Unpacked authenticated UUID from authorization token.
        service: Injected core BankQuestionService layer handling validations.

    Returns:
        Standard structured APIResponse marking operations successfully complete natively.

    Raises:
        BankAccessDeniedError: User fails permission constraint testing natively.
        BankQuestionAlreadyExistsError: Overlapping target arrays encountered.
    """
    await service.add_questions_to_bank(bank_id, payload.question_ids, user_id)
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
    """Remove multiple linked questions from a bank.

    Validates edit permissions before natively severing the structural associative relationship
    between the provided array endpoints cleanly from the database layer.

    Args:
        request: The FastAPI execution request context.
        bank_id: Primary UUID targeting the active Bank.
        payload: The JSON representation containing targets mapped to unlink.
        user_id: Unpacked authenticated UUID from authorization token.
        service: Injected core BankQuestionService layer handling checks.

    Returns:
        Standard structured APIResponse confirming removal statuses accurately.

    Raises:
        BankAccessDeniedError: User fails requisite explicit permission bounds checking natively.
        BankQuestionNotFoundError: Encountering subsets of question definitions unmapped locally.
    """
    await service.remove_questions_from_bank(bank_id, payload.question_ids, user_id)
    return create_api_response(
        request, message="Questions removed from bank successfully"
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
    """Retrieve a summary list of questions associated with a bank.

    Validates read capabilities before streaming paginated results explicitly mapping
    into native JSON arrays across target bank sets.

    Args:
        request: The FastAPI execution context.
        bank_id: Primary UUID targeting the active Bank.
        skip: Standard numerical subset offset slice.
        limit: Max depth returned native rows.
        user_id: Intercepted authorization token mapping mapping.
        service: BankQuestionService orchestrating standard reads.

    Returns:
        Standard structured APIResponse injecting nested list item payload models internally.

    Raises:
        BankNotFoundError: If target entity ID lacks tracking representations natively.
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
    """Retrieve detailed information of a specific question inside a bank.

    Verifies associative relationship targets confirming read-access constraints before
    supplying deep structural test evaluations and context logic configurations cleanly.

    Args:
        request: FastAPI routing metadata tracker natively mapping explicit values.
        bank_id: Top-level constraint filter binding definitions properly.
        question_id: Lower-level constraint targeted lookup exactly matching relations.
        user_id: Validated owner or permission read constraint targets.
        service: Injected backend Service resolving data models.

    Returns:
        Standard structural APIResponse nesting completely populated subset representations explicitly.

    Raises:
        QuestionNotFoundError: Underlying question ID natively untracked globally.
        BankQuestionNotFoundError: Associative linking targets evaluating false explicitly.
    """
    question = await service.get_bank_question(bank_id, question_id, user_id)
    return create_api_response(
        request,
        data=question.model_dump(),
        message="Bank question fetched successfully",
    )
