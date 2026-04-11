"""Judge0-specific exceptions."""

from typing import Optional


class Judge0ClientError(Exception):
    """Base exception for Judge0 client errors."""

    pass


class Judge0APIError(Judge0ClientError):
    """Judge0 API returned an error."""

    def __init__(
        self, status_code: int, detail: str, request_id: Optional[str] = None
    ):
        self.status_code = status_code
        self.detail = detail
        self.request_id = request_id
        super().__init__(
            f"Judge0 API Error ({status_code}): {detail} [request_id={request_id}]"
        )


class Judge0TimeoutError(Judge0ClientError):
    """Judge0 request timed out."""

    pass


class Judge0ConnectionError(Judge0ClientError):
    """Failed to connect to Judge0."""

    pass


class Judge0ServiceUnavailableError(Judge0ClientError):
    """Judge0 service is temporarily unavailable."""

    pass
