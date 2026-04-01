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

    def __init__(self, bank_id: str | None = None):
        """Initialize the permission error exception."""
        super().__init__(
            message=f"User lacks required permissions on bank with ID {bank_id}"
            if bank_id
            else "User lacks required permissions",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class BankQuestionNotFoundError(AppBaseException):
    """Exception raised when a requested question is not found in a bank.

    This error is thrown when an operation attempts to unlink, access,
    or modify a question that has not been structurally bound to the bank.
    """

    def __init__(self, bank_id: str, question_id: str):
        """Initialize the exception with the missing link's IDs.

        Args:
            bank_id (str): The unique identifier of the bank.
            question_id (str): The unique identifier of the question.
        """
        super().__init__(
            message=f"Question {question_id} not found in bank {bank_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class BankQuestionAlreadyExistsError(AppBaseException):
    """Exception raised when linking a question to a bank that's already linked.

    This error enforces uniqueness on questions bound to a bank, preventing
    duplicate association rows in bulk inserts.
    """

    def __init__(self, bank_id: str, question_id: str):
        """Initialize the exception with the conflicting IDs.

        Args:
            bank_id (str): The bank ID where the conflict occurred.
            question_id (str): The question ID that already exists in the bank.
        """
        super().__init__(
            message=f"Question {question_id} is already in bank {bank_id}",
            status_code=status.HTTP_409_CONFLICT,
        )
