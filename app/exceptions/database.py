from fastapi import status

from app.exceptions.base import AppBaseException


class DatabaseUnavailableError(AppBaseException):
    """Exception raised when the database connection is unhealthy."""

    def __init__(self, detail: str = "Database connection failed"):
        super().__init__(
            message="Service Unavailable: Database connection failed",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )
