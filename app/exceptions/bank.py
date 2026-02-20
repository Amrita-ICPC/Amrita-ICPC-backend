from fastapi import status

from app.exceptions.base import AppBaseException


class BankNotFoundError(AppBaseException):
    """Exception raised when a requested bank is not found.

    This error is thrown when an operation attempts to access or modify
    a bank that does not exist in the database or has been deleted.
    """

    def __init__(self, bank_id: str):
        """Initialize the exception with the missing bank's ID.

        Args:
            bank_id (str): The unique identifier of the bank that was not found.
        """
        super().__init__(
            message=f"Bank with ID {bank_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class BankAlreadyExistsError(AppBaseException):
    """Exception raised when attempting to create a bank that already exists.

    This error is thrown to enforce uniqueness constraints, typically
    preventing a user from creating multiple banks with the exact same name.
    """

    def __init__(self, name: str):
        """Initialize the exception with the conflicting bank name.

        Args:
            name (str): The name of the bank that caused the conflict.
        """
        super().__init__(
            message=f"Bank with name '{name}' already exists",
            status_code=status.HTTP_409_CONFLICT,
        )


class BankAccessDeniedError(AppBaseException):
    """Exception raised when a user has absolutely no access to a bank.

    This error is thrown when a user attempts to view or interact with
    a bank that they do not own and which has not been shared with them.
    """

    def __init__(self):
        """Initialize the access denied exception."""
        super().__init__(
            message="You do not have permission to access this bank",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class BankPermissionError(AppBaseException):
    """Exception raised when a user lacks the specific permission for an action.

    This error is thrown when a user has some access to a bank (e.g., READ),
    but attempts an operation that requires a higher permission level (e.g., EDIT or OWNER).
    """

    def __init__(self):
        """Initialize the permission error exception."""
        super().__init__(
            message="You do not have permission to perform this action",
            status_code=status.HTTP_403_FORBIDDEN,
        )
