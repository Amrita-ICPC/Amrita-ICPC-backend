from app.schema.base import PaginationResponse


def get_pagination(total: int, page: int, page_size: int) -> PaginationResponse:
    """
    Calculate and return a PaginationResponse.

    Args:
        total: Total number of items
        page: Current page number (1-indexed)
        page_size: Number of items per page

    Returns:
        PaginationResponse object with calculated pagination metadata
    """
    skip = (page - 1) * page_size
    return PaginationResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if page_size else 0,
        has_next=skip + page_size < total,
        has_previous=page > 1,
    )
