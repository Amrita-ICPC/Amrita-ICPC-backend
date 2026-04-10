from collections.abc import Mapping, Sequence

from app.exceptions.question import InvalidQuestionError
from app.repositories.language import LanguageRepository


class QuestionValidator:
    """Validator for question business rules and constraints."""

    @staticmethod
    def validate_testcases_format(testcases: Sequence[object]) -> None:
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
            if isinstance(tc, Mapping):
                testcase = tc
            elif callable(getattr(tc, "model_dump", None)):
                try:
                    dumped = tc.model_dump()  # type: ignore[attr-defined]
                    if not isinstance(dumped, Mapping):
                        raise InvalidQuestionError(
                            f"Testcase at index {i} must be an object"
                        )
                    testcase = dumped
                except (TypeError, Exception) as e:
                    raise InvalidQuestionError(
                        f"Testcase at index {i} must be an object: {str(e)}"
                    )
            else:
                raise InvalidQuestionError(f"Testcase at index {i} must be an object")
            if "input" not in testcase:
                raise InvalidQuestionError(
                    f"Testcase at index {i} missing 'input' field"
                )
            # We assume output can be optional or required depending on the judging logic,
            # but usually it's required for standard ICPC questions. We'll enforce it here.
            if "output" not in testcase:
                raise InvalidQuestionError(
                    f"Testcase at index {i} missing 'output' field"
                )
            if "is_hidden" not in testcase:
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
    def validate_allowed_languages(languages: list[int] | None) -> None:
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

    @staticmethod
    async def validate_platform_languages_exist(
        language_repository: LanguageRepository,
        *,
        allowed_language_ids: list[int],
        template_language_ids: list[int],
    ) -> None:
        """Validate that all referenced language IDs exist in platform languages."""
        all_requested_ids = set(allowed_language_ids) | set(template_language_ids)
        existing_ids = await language_repository.get_existing_ids(all_requested_ids)
        missing_allowed_ids = sorted(set(allowed_language_ids) - existing_ids)
        if missing_allowed_ids:
            missing = ", ".join(str(language_id) for language_id in missing_allowed_ids)
            raise InvalidQuestionError(
                f"Allowed language IDs are not configured in platform languages: {missing}"
            )

        missing_template_ids = sorted(set(template_language_ids) - existing_ids)
        if missing_template_ids:
            missing = ", ".join(
                str(language_id) for language_id in missing_template_ids
            )
            raise InvalidQuestionError(
                f"Template language IDs are not configured in platform languages: {missing}"
            )
