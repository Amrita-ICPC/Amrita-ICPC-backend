"""
Data Transfer Objects for student operations.
These are INTERNAL formats used between layers.
NOT exposed to API users.
"""

from uuid import UUID
from dataclasses import dataclass


@dataclass
class PublicContestFilterData:
    """
    When SERVICE wants to query public contests, it creates THIS object
    and passes it to REPOSITORY.
    
    Example usage in service:
    filters = PublicContestFilterData(
        search_term="ICPC",
        status="SCHEDULED",
        skip=0,
        limit=10
    )
    total, contests = await repo.get_public_contests(filters)
    """
    search_term: str | None = None
    status: str | None = None
    skip: int = 0
    limit: int = 10