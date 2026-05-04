from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.utils.enums import BankQuestionSortBy, QuestionDifficulty, SortOrder


@dataclass
class BankFilters:
    """Filters applied when querying banks.

    This DTO is used to pass filtering criteria from the service
    layer down to the repository layer.

    Attributes:
        search_term: Text to search for within the bank name.
    """

    search_term: Optional[str] = None


@dataclass
class BankQuestionFilters:
    """Filters for querying questions inside a bank."""

    title: Optional[str] = None
    difficulty: Optional[QuestionDifficulty] = None
    tag: Optional[str] = None
    sort_by: Optional[BankQuestionSortBy] = BankQuestionSortBy.NAME
    sort_order: SortOrder = SortOrder.ASC
