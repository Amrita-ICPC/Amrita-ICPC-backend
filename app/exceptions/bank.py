from fastapi import status

from app.exceptions.base import AppBaseException


class BankNotFoundError(AppBaseException):
    def __init__(self, bank_id: str):
        super().__init__(
            message=f"Bank with ID {bank_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class BankAlreadyExistsError(AppBaseException):
    def __init__(self, name: str):
        super().__init__(
            message=f"Bank with name '{name}' already exists",
            status_code=status.HTTP_409_CONFLICT,
        )


class BankAccessDeniedError(AppBaseException):
    def __init__(self):
        super().__init__(
            message="You do not have permission to access this bank",
            status_code=status.HTTP_403_FORBIDDEN,
        )

class BankPermissionError(AppBaseException):
    def __init__(self):
        super().__init__(
            message="You do not have permission to perform this action",
            status_code=status.HTTP_403_FORBIDDEN,
        )

