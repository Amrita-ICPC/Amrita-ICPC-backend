from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.models.question import Question, QuestionTemplate
    from app.schema.question import (
        QuestionAndTestcasesResponse,
        QuestionTemplateResponse,
    )

from app.exceptions.question import InvalidQuestionError
from app.repositories.language import LanguageRepository
from app.schema.question import UpdateQuestionMetadataRequest


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

    @staticmethod
    def validate_unique_testcase_ids(testcase_ids: list[UUID]) -> None:
        """Validate that testcase IDs in a bulk request are unique."""
        if len(set(testcase_ids)) != len(testcase_ids):
            raise InvalidQuestionError("Duplicate testcase IDs are not allowed")

    @staticmethod
    def validate_unique_template_language_ids(language_ids: list[int]) -> None:
        """Validate that template language IDs in a bulk request are unique."""
        if len(set(language_ids)) != len(language_ids):
            raise InvalidQuestionError(
                "Duplicate template language IDs are not allowed"
            )

    @staticmethod
    def validate_question_testcases_exist(
        existing_testcase_ids: set[UUID], testcase_ids: list[UUID]
    ) -> None:
        """Validate that all requested testcase IDs belong to the question."""
        missing_ids = [
            testcase_id
            for testcase_id in testcase_ids
            if testcase_id not in existing_testcase_ids
        ]
        if missing_ids:
            raise InvalidQuestionError(
                f"Testcase ID {missing_ids[0]} does not belong to the question"
            )

    @staticmethod
    def validate_question_template_languages_exist(
        existing_language_ids: set[int], language_ids: list[int]
    ) -> None:
        """Validate that all requested template language IDs belong to the question."""
        missing_ids = [
            language_id
            for language_id in language_ids
            if language_id not in existing_language_ids
        ]
        if missing_ids:
            raise InvalidQuestionError(
                f"Template language ID {missing_ids[0]} does not belong to the question"
            )

    @staticmethod
    def validate_metadata_update(metadata: UpdateQuestionMetadataRequest) -> None:
        """Validate metadata fields in an update request.

        Checks that time/memory limits are positive if provided and that
        at least one field is provided for the update.

        Args:
            metadata: Metadata update request.

        Raises:
            InvalidQuestionError: If metadata contains invalid values.
        """
        QuestionValidator.validate_limits(
            metadata.time_limit_ms, metadata.memory_limit_mb
        )
        QuestionValidator.validate_allowed_languages(metadata.allowed_languages)

        # Ensure at least one field is specified for update
        has_update = any(
            [
                metadata.question_text is not None,
                metadata.difficulty is not None,
                metadata.time_limit_ms is not None,
                metadata.memory_limit_mb is not None,
                metadata.allowed_languages is not None,
                metadata.tag_ids is not None,
            ]
        )
        if not has_update:
            raise InvalidQuestionError(
                "At least one metadata field must be provided for update"
            )

    @staticmethod
    def validate_submission_language(
        question: "Question | QuestionAndTestcasesResponse", language_id: int
    ) -> "QuestionTemplate | QuestionTemplateResponse":
        """Validate that the question supports the given language.

        Args:
            question: The question to validate against.
            language_id: The language ID from the submission.

        Returns:
            The QuestionTemplate or QuestionTemplateResponse for the specified language.

        Raises:
            InvalidQuestionError: If the template for the language does not exist.
        """
        for template in question.templates:
            if template.language_id == language_id:
                return template
        raise InvalidQuestionError(
            f"Language ID {language_id} is not supported for this question"
        )
