"""Data Transfer Objects for user repository operations."""

from dataclasses import dataclass

from app.repositories.dto.pagination import PaginationParams
from app.utils.enums import UserRole


@dataclass
class UserListFilters(PaginationParams):
    """DTO for user list filtering and pagination."""

    role: UserRole | None = None
    query: str | None = None
