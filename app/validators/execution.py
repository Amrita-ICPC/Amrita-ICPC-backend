# app/validators/execution.py
"""Validator for code execution business rules and constraints.

Implements the Validator Pattern for execution operations, centralizing all
business rule validation for code submissions to ensure data integrity and
enforce domain-specific constraints.
"""

from app.exceptions.execution import (
    InvalidCodeError,
    InvalidLanguageError,
    InvalidSubmissionTokenError,
)


class ExecutionValidator:
    """Validator for code execution and submission business rules.

    This class centralizes business rule validation for code execution operations,
    ensuring that submissions meet domain constraints before being sent to Judge0.

    Responsibilities:
        - Validate source code size and content
        - Validate programming language IDs
        - Validate standard input constraints
        - Validate submission tokens

    Design Principles:
        - Single Responsibility: Only handles business rule validation
        - Stateless: All methods are static (no instance state)
        - Fail Fast: Raises domain exceptions immediately on violation
        - Reusable: Called by service layer before execution

    Validation Methods:
        - validate_source_code: Enforces size limits and content rules
        - validate_language_id: Validates language ID is positive
        - validate_stdin: Validates standard input constraints
        - validate_token: Validates submission token format

    Exception Strategy:
        - Raises domain-specific exceptions (InvalidCodeError, etc.)
        - Provides clear error messages with context
        - Never modifies state (validation only)
    """

    # Configuration constants
    MAX_SOURCE_CODE_SIZE = 50000  # 50KB
    MAX_STDIN_SIZE = 10000  # 10KB
    MIN_LANGUAGE_ID = 1
    MAX_LANGUAGE_ID = 100  # Judge0 typically has <100 supported languages

    @staticmethod
    def validate_source_code(source_code: str) -> None:
        """
        Validate source code meets business constraints.

        Args:
            source_code: The source code to validate

        Raises:
            InvalidCodeError: If code violates constraints
        """
        if not source_code:
            raise InvalidCodeError("Source code cannot be empty")

        if not isinstance(source_code, str):
            raise InvalidCodeError("Source code must be a string")

        if len(source_code) > ExecutionValidator.MAX_SOURCE_CODE_SIZE:
            raise InvalidCodeError(
                f"Source code exceeds maximum size of {ExecutionValidator.MAX_SOURCE_CODE_SIZE} bytes. "
                f"Provided: {len(source_code)} bytes"
            )

        if not source_code.strip():
            raise InvalidCodeError(
                "Source code cannot contain only whitespace characters"
            )

    @staticmethod
    def validate_language_id(language_id: int) -> None:
        """
        Validate programming language ID is within acceptable range.

        Args:
            language_id: Judge0 language ID to validate

        Raises:
            InvalidLanguageError: If language ID is invalid
        """
        if not isinstance(language_id, int):
            raise InvalidLanguageError(
                f"Language ID must be an integer, got {type(language_id).__name__}"
            )

        if language_id < ExecutionValidator.MIN_LANGUAGE_ID:
            raise InvalidLanguageError(
                f"Language ID must be >= {ExecutionValidator.MIN_LANGUAGE_ID}, got {language_id}"
            )

        if language_id > ExecutionValidator.MAX_LANGUAGE_ID:
            raise InvalidLanguageError(
                f"Language ID must be <= {ExecutionValidator.MAX_LANGUAGE_ID}, got {language_id}. "
                f"Contact support if you believe this is incorrect."
            )

    @staticmethod
    def validate_stdin(stdin: str | None) -> None:
        """
        Validate standard input meets size constraints.

        Args:
            stdin: Standard input to validate (optional)

        Raises:
            InvalidCodeError: If stdin violates constraints
        """
        if stdin is None:
            return  # stdin is optional

        if not isinstance(stdin, str):
            raise InvalidCodeError(
                f"Standard input must be a string, got {type(stdin).__name__}"
            )

        if len(stdin) > ExecutionValidator.MAX_STDIN_SIZE:
            raise InvalidCodeError(
                f"Standard input exceeds maximum size of {ExecutionValidator.MAX_STDIN_SIZE} bytes. "
                f"Provided: {len(stdin)} bytes"
            )

    @staticmethod
    def validate_token(token: str) -> None:
        """
        Validate submission token format and content.

        Args:
            token: Submission token to validate

        Raises:
            InvalidSubmissionTokenError: If token is invalid
        """
        if not token:
            raise InvalidSubmissionTokenError("Submission token cannot be empty")

        if not isinstance(token, str):
            raise InvalidSubmissionTokenError(
                f"Token must be a string, got {type(token).__name__}"
            )

        if not token.strip():
            raise InvalidSubmissionTokenError(
                "Submission token cannot contain only whitespace"
            )

        if len(token) > 100:
            raise InvalidSubmissionTokenError(
                f"Submission token exceeds maximum length of 100 characters. Got {len(token)}"
            )

        # Judge0 tokens are typically base64-like or UUID format
        # Basic validation: should contain alphanumeric and common token chars
        invalid_chars = set(token) - set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        )
        if invalid_chars:
            raise InvalidSubmissionTokenError(
                f"Token contains invalid characters: {invalid_chars}"
            )

    @staticmethod
    def validate_submission_request(
        source_code: str,
        language_id: int,
        stdin: str | None = None,
    ) -> None:
        """
        Validate complete submission request (all fields together).

        This is the primary validation entry point that validates all
        submission fields against business rules.

        Args:
            source_code: Source code to execute
            language_id: Judge0 language ID
            stdin: Standard input (optional)

        Raises:
            InvalidCodeError: If any field violates constraints
            InvalidLanguageError: If language ID is invalid
        """
        ExecutionValidator.validate_source_code(source_code)
        ExecutionValidator.validate_language_id(language_id)
        ExecutionValidator.validate_stdin(stdin)
