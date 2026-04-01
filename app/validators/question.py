from typing import Any

from app.exceptions.question import InvalidQuestionError


class QuestionValidator:
    """Validator for question business rules and constraints."""

    @staticmethod
    def validate_testcases_format(testcases: list[dict[str, Any]]) -> None:
        """
        Validates the format of testcases to ensure they contain required fields.

        Args:
            testcases: List of testcase dictionaries.

        Raises:
            InvalidQuestionError: If testcases format is invalid.
        """
        if not testcases:
            raise InvalidQuestionError("At least one testcase is required")

        for i, tc in enumerate(testcases):
            if not isinstance(tc, dict):
                raise InvalidQuestionError(f"Testcase at index {i} must be an object")
            if "input" not in tc:
                raise InvalidQuestionError(
                    f"Testcase at index {i} missing 'input' field"
                )
            # We assume output can be optional or required depending on the judging logic,
            # but usually it's required for standard ICPC questions. We'll enforce it here.
            if "output" not in tc:
                raise InvalidQuestionError(
                    f"Testcase at index {i} missing 'output' field"
                )
            if "is_hidden" not in tc:
                raise InvalidQuestionError(
                    f"Testcase at index {i} missing 'is_hidden' field"
                )

    @staticmethod
    def validate_limits(time_limit_ms: int | None, memory_limit_mb: int | None) -> None:
        """
        Validates that time and memory limits are positive.

        Args:
            time_limit_ms: Time limit in ms
            memory_limit_mb: Memory limit in mb

        Raises:
            InvalidQuestionError: If limits are not strictly positive integers.
        """
        if time_limit_ms is not None and time_limit_ms <= 0:
            raise InvalidQuestionError("Time limit must be greater than 0 ms")
        if memory_limit_mb is not None and memory_limit_mb <= 0:
            raise InvalidQuestionError("Memory limit must be greater than 0 MB")

    @staticmethod
    def validate_allowed_languages(languages: list[str] | None) -> None:
        """
        Validates the allowed languages list.

        Args:
            languages: List of allowed languages.

        Raises:
            InvalidQuestionError: If the list is empty.
        """
        if languages is not None and not languages:
            raise InvalidQuestionError(
                "At least one allowed language must be specified"
            )
