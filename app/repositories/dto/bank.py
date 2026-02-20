from dataclasses import dataclass
from typing import Optional


@dataclass
class BankFilters:
    """Filters applied when querying banks.

    This DTO is used to pass filtering criteria from the service
    layer down to the repository layer.

    Attributes:
        search_term: Text to search for within the bank name.
    """

    search_term: Optional[str] = None
