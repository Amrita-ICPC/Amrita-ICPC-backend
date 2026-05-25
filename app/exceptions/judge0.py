"""Judge0-specific exceptions."""

from typing import Optional

from app.exceptions.base import AppBaseException


class Judge0ClientError(AppBaseException):
    """Base exception for Judge0 client errors."""

    def __init__(
        self, message: str, status_code: int = 502, detail: Optional[str] = None
    ):
        super().__init__(message=message, status_code=status_code, detail=detail)


class Judge0APIError(Judge0ClientError):
    """Judge0 API returned an error."""

    def __init__(
        self, status_code: int, detail: str, request_id: Optional[str] = None
    ):
        self.request_id = request_id
        message = f"Judge0 API Error ({status_code}): {detail}"
        if request_id:
            message += f" [request_id={request_id}]"
        super().__init__(message=message, status_code=status_code, detail=detail)


class Judge0TimeoutError(Judge0ClientError):
    """Judge0 request timed out."""

    def __init__(self, message: str = "Judge0 request timed out"):
        super().__init__(message=message, status_code=502)


class Judge0ConnectionError(Judge0ClientError):
    """Failed to connect to Judge0."""

    def __init__(self, message: str = "Failed to connect to Judge0"):
        super().__init__(message=message, status_code=502)


class Judge0ServiceUnavailableError(Judge0ClientError):
    """Judge0 service is temporarily unavailable."""

    def __init__(self, message: str = "Judge0 service is temporarily unavailable"):
        super().__init__(message=message, status_code=502)


class Judge0NotInitializedError(Judge0ClientError):
    """Judge0 client is not initialized (service disabled)."""

    def __init__(
        self,
        message: str = "Judge0 service is not configured or disabled"
    ):
        super().__init__(
            message=message,
            status_code=503,  # Service Unavailable
            detail="Judge0 is not available. Please contact the administrator."
        )
