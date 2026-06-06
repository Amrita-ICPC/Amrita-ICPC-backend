from uuid import UUID

from app.models.bank import Bank
from app.repositories.dto.bank import BankFilters
from app.repositories.dto.pagination import PaginationParams
from app.schema.bank import BankDetailResponse, BankResponse
from app.utils.enums import BankSortBy, QuestionDifficulty


def build_bank_query_params(
    *,
    skip: int,
    limit: int,
    search_term: str | None = None,
    sort_by: BankSortBy | None = None,
) -> tuple[BankFilters, PaginationParams]:
    """Build repository filter and pagination DTOs for bank queries."""
    return BankFilters(search_term=search_term, sort_by=sort_by), PaginationParams(
        skip=skip, limit=limit
    )


def to_bank_response(bank: "Bank") -> BankResponse:
    """Map bank ORM object to response schema."""
    return BankResponse.model_validate(bank)


def to_bank_response_list(banks: list["Bank"]) -> list[BankResponse]:
    """Map bank ORM list to response schema list."""
    return [to_bank_response(bank) for bank in banks]


def to_bank_detail_response(bank: "Bank") -> BankDetailResponse:
    """Map bank ORM object to detail response schema."""
    questions = bank.questions or []

    total_count = len(questions)
    easy_count = 0
    medium_count = 0
    hard_count = 0

    for link in questions:
        if link.question:
            if link.question.difficulty == QuestionDifficulty.EASY:
                easy_count += 1
            elif link.question.difficulty == QuestionDifficulty.MEDIUM:
                medium_count += 1
            elif link.question.difficulty == QuestionDifficulty.HARD:
                hard_count += 1

    shares = bank.shares or []

    return BankDetailResponse(
        id=bank.id,
        name=bank.name,
        description=bank.description,
        created_by=bank.created_by,
        created_at=bank.created_at,
        updated_at=bank.updated_at,
        total_questions_count=total_count,
        easy_questions_count=easy_count,
        medium_questions_count=medium_count,
        hard_questions_count=hard_count,
        shared_users_count=len([s for s in shares if s.user_id != bank.created_by]),
    )


def clone_bank_detail_response(bank_detail: BankDetailResponse) -> BankDetailResponse:
    """Create a defensive copy of cached bank detail response."""
    return bank_detail.model_copy(deep=True)


def build_bank_entity(*, name: str, description: str | None, user_id: UUID) -> Bank:
    """Map validated bank payload to ORM entity."""
    return Bank(
        name=name,
        description=description,
        created_by=user_id,
        is_deleted=False,
    )
