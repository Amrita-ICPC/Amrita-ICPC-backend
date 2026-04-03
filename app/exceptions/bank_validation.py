from fastapi import status

from app.exceptions.base import AppBaseException


class BankValidationError(AppBaseException):
    """Exception raised when bank-specific business validation fails."""

    def __init__(self, message: str):
        super().__init__(
            message=f"Invalid bank data: {message}",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
