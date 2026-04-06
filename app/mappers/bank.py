from uuid import UUID

from app.models.bank import Bank
from app.repositories.dto.bank import BankFilters
from app.repositories.dto.pagination import PaginationParams
from app.schema.bank import BankDetailResponse, BankResponse, BankShareBase
from app.schema.question import QuestionResponse


def build_bank_query_params(
    *,
    skip: int,
    limit: int,
    search_term: str | None = None,
) -> tuple[BankFilters, PaginationParams]:
    """Build repository filter and pagination DTOs for bank queries."""
    return BankFilters(search_term=search_term), PaginationParams(
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
    question_items = [
        QuestionResponse.from_question(link.question)
        for link in (bank.questions or [])
        if link.question is not None
    ]

    return BankDetailResponse(
        id=bank.id,
        name=bank.name,
        description=bank.description,
        created_by=bank.created_by,
        created_at=bank.created_at,
        updated_at=bank.updated_at,
        questions=question_items,
        shares=[
            BankShareBase(user_id=share.user_id, permission=share.permission)
            for share in (bank.shares or [])
        ],
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
