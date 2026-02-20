from datetime import datetime, timezone
from typing import Any

from fastapi import Request, status

from app.schema.base import APIResponse, MetaResponse, PaginationResponse


def create_api_response(
    request: Request,
    data: Any = None,
    message: str = "Success",
    status_code: int = status.HTTP_200_OK,
    success: bool = True,
    pagination: PaginationResponse | None = None,
) -> APIResponse:
    """
    Create a standardized API response.

    Args:
        request: The FastAPI request object (used to extract request_id).
        data: The data payload.
        message: A descriptive message.
        status_code: HTTP status code.
        success: Boolean indicating success or failure.
        pagination: Pagination details if applicable.

    Returns:
        An instance of APIResponse.
    """
    request_id = getattr(request.state, "request_id", "unknown")

    # Use UTC aware datetime as requested
    timestamp = datetime.now(timezone.utc)

    meta = MetaResponse(
        request_id=request_id,
        timestamp=timestamp,
    )

    return APIResponse(
        success=success,
        status=status_code,
        message=message,
        data=data,
        pagination=pagination,
        meta=meta,
    )
