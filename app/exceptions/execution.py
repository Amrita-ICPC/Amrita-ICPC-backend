"""Exceptions for code execution and submission operations.

This module contains all domain-specific exceptions related to code execution,
submission validation, and Judge0 integration failures.
"""

from fastapi import status

from app.exceptions.base import AppBaseException


class InvalidCodeError(AppBaseException):
    """Exception raised when source code fails domain validation.

    Raised when code submission violates business rules such as:
    - Source code exceeds size limits
    - Source code is empty or only whitespace
    - Code format is invalid
    """

    def __init__(self, message: str):
        super().__init__(
            message=f"Invalid code submission: {message}",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class InvalidLanguageError(AppBaseException):
    """Exception raised when programming language ID is invalid.

    Raised when:
    - Language ID is out of acceptable range (1-100)
    - Language ID is not a valid integer
    - Language is not supported by Judge0
    """

    def __init__(self, message: str):
        super().__init__(
            message=f"Invalid language selection: {message}",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class InvalidSubmissionTokenError(AppBaseException):
    """Exception raised when submission token is invalid or malformed.

    Raised when:
    - Token is empty or contains only whitespace
    - Token format is invalid (contains invalid characters)
    - Token exceeds maximum length
    - Token cannot be parsed or recognized
    """

    def __init__(self, message: str):
        super().__init__(
            message=f"Invalid submission token: {message}",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class CodeExecutionError(AppBaseException):
    """Exception raised when code execution fails on Judge0.

    Raised when:
    - Judge0 submission fails
    - Judge0 returns a service error
    - Execution times out
    - Cannot retrieve execution results
    """

    def __init__(self, message: str = "Code execution failed"):
        super().__init__(
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


class NoTestCasesError(AppBaseException):
    """Exception raised when a question has no non-hidden test cases.

    Raised when attempting to run code against a question that has no
    visible test cases for students to practice against.
    """

    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class CompilationError(AppBaseException):
    """Exception raised when code fails to compile.

    Raised when:
    - Code has syntax errors
    - Code has import errors
    - Code fails to parse by the compiler

    This is used in practice runs to signal early exit without running test cases.
    """

    def __init__(self, compile_output: str):
        """Initialize with compilation error output.

        Args:
            compile_output: Error details from Judge0 compiler
        """
        self.compile_output = compile_output
        super().__init__(
            message=f"Code has compilation errors: {compile_output}",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
