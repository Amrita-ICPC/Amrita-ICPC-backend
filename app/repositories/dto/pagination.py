# app/domain/pagination.py
from dataclasses import dataclass


@dataclass
class PaginationParams:
    """
    Reusable pagination parameters passed to repository.
    Lives in domain layer — not tied to FastAPI or SQLAlchemy.
    """

    skip: int = 0
    limit: int = 100

    def __post_init__(self):
        if self.skip < 0:
            raise ValueError("skip must be >= 0")
        if self.limit < 1:
            raise ValueError("limit must be >= 1")
        if self.limit > 100:
            self.limit = 100  # hard cap


@dataclass
class PaginatedResult:
    """
    Generic paginated result returned from repository.
    Service maps this to the response schema.
    """

    total: int
    items: list
