import asyncio
import uuid
from typing import List
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get
from app.core.storage import CodeStorageService
from app.exceptions.bank import (
    BankQuestionNotFoundError,
)
from app.exceptions.question import CodeStorageError
from app.mappers.bank_question import (
    to_bank_question_metadata_responses,
    to_bank_question_response,
)
from app.mappers.question import (
    apply_question_updates,
    build_template_dto,
    build_update_question_dto,
    build_update_testcase_dtos,
)
from app.models.question import Question
from app.repositories.bank import BankRepository
from app.repositories.dto import (
    BankQuestionFilters,
    CreateQuestionTemplateData,
    PaginationParams,
)
from app.repositories.language import LanguageRepository
from app.repositories.question import QuestionRepository
from app.schema.question import (
    BankQuestionMetadataResponse,
    QuestionResponse,
    QuestionUpdate,
)
from app.utils.question_clone import deep_copy_question_for_clone
from app.validators.bank import BankValidator
from app.validators.bank_question import BankQuestionValidator
from app.validators.question import QuestionValidator


class BankQuestionService:
    """Service layer for bank-question linking and retrieval operations.

    This service coordinates bank access checks, question linkage validation,
    paginated retrieval, and template code hydration. It delegates persistence to
    repositories and applies domain checks via validators.

    Responsibilities:
        - Link and unlink question associations for banks
        - Validate bank read/edit permissions through BankValidator
        - Return paginated question summaries for bank-scoped listings
        - Resolve template code object keys from storage on detail reads
        - Invalidate and populate cache entries for bank-question views
    """

    def __init__(
        self,
        repository: BankRepository,
        question_repo: QuestionRepository,
        validator: BankValidator,
        code_storage_service: CodeStorageService,
        language_repo: LanguageRepository,
    ):
        """Initialize bank-question service dependencies.

        Args:
            repository: Bank repository for association and bank access operations.
            question_repo: Question repository for question entity retrieval.
            validator: Bank validator for read/edit permission checks.
            code_storage_service: Storage service used to fetch template code payloads.
        """
        self.repository = repository
        self.question_repo = question_repo
        self.validator = validator
        self.code_storage_service = code_storage_service
        self.language_repo = language_repo

    def _get_bank_question_cache_keys(self, bank_id: UUID) -> list[str]:
        """Build cache keys and patterns for bank-question invalidation.

        Args:
            bank_id: Target bank ID.

        Returns:
            List of key patterns affected by association mutations.
        """
        return [
            f"bank:{bank_id}",
            f"banks:questions:v2:{bank_id}:*",
            f"bank:question:v2:{bank_id}:*",
            f"banks:questions:{bank_id}:*",
            f"bank:question:{bank_id}:*",
        ]

    @staticmethod
    def _is_storage_object_key(value: str | None) -> bool:
        """Check whether a value is a storage object key."""
        return bool(value and value.startswith("code/"))

    async def _resolve_code_field(self, value: str | None) -> str | None:
        """Resolve storage object keys to plain code text.

        Args:
            value: Template code field value.

        Returns:
            Plain code text when value is a storage key, otherwise original value.

        Raises:
            CodeStorageError: If object retrieval fails.
        """
        if not self._is_storage_object_key(value):
            return value
        assert value is not None
        try:
            return await self.code_storage_service.get_code(value)
        except Exception as error:
            raise CodeStorageError(
                f"Failed to fetch code payload from storage: {error}"
            ) from error

    async def _hydrate_question_template_codes(
        self, question_response: QuestionResponse
    ) -> QuestionResponse:
        """Hydrate template fields in a response using object storage.

        Args:
            question_response: Bank-scoped question response.

        Returns:
            Hydrated response with plain code in template fields.

        Raises:
            CodeStorageError: If any object-key fetch fails.
        """
        for template in question_response.templates:
            starter_code, driver_code, solution_code = await asyncio.gather(
                self._resolve_code_field(template.starter_code),
                self._resolve_code_field(template.driver_code),
                self._resolve_code_field(template.solution_code),
            )
            template.starter_code = starter_code or ""
            template.driver_code = driver_code
            template.solution_code = solution_code
        return question_response

    @cache_delete(
        key_builder=lambda self,
        bank_id,
        *args,
        **kwargs: self._get_bank_question_cache_keys(bank_id)
    )
    async def add_questions_to_bank(
        self, bank_id: UUID, question_ids: List[UUID], user_id: UUID
    ) -> None:
        """Link existing questions to a bank.

        Args:
            bank_id: Target bank ID.
            question_ids: Question IDs to associate with the bank.
            user_id: Authenticated user performing the operation.

        Raises:
            BankNotFoundError: If bank does not exist.
            BankAccessDeniedError: If user cannot edit the bank.
            QuestionNotFoundError: If any question is missing.
            BankQuestionAlreadyExistsError: If link already exists.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        self.validator.check_edit_bank(user_id=user_id, bank=bank)

        BankQuestionValidator.validate_unique_question_ids(question_ids)

        await self.question_repo.validate_questions_exist(question_ids)

        existing = await self.repository.get_questions_in_bank_by_ids(
            bank_id, question_ids
        )
        BankQuestionValidator.validate_question_already_exist(
            existing, bank_id, question_ids
        )

        await self.repository.add_questions_to_bank(bank_id, question_ids, user_id)

    @cache_delete(
        key_builder=lambda self,
        source_bank_id,
        target_bank_id,
        *args,
        **kwargs: self._get_bank_question_cache_keys(source_bank_id)
        + self._get_bank_question_cache_keys(target_bank_id)
    )
    async def clone_questions_between_banks(
        self,
        source_bank_id: UUID,
        target_bank_id: UUID,
        user_id: UUID,
        *,
        copy_all: bool,
        question_ids: List[UUID] | None,
    ) -> int:
        """Clone questions from a source bank into a target bank.

        Performs permission checks, source membership validation, deep-copy creation,
        and bulk persistence/linking.
        """
        BankQuestionValidator.validate_clone_questions(
            source_bank_id,
            target_bank_id,
            question_ids,
            copy_all,
        )

        source_bank = await self.repository.get_bank_or_raise(
            source_bank_id, load_relations=True
        )
        self.validator.check_read_bank(user_id=user_id, bank=source_bank)

        target_bank = await self.repository.get_bank_or_raise(
            target_bank_id, load_relations=True
        )
        self.validator.check_edit_bank(user_id=user_id, bank=target_bank)

        source_questions: List[Question]
        if copy_all:
            source_questions = await self.repository.get_all_question_entities_in_bank(
                source_bank_id
            )
        else:
            selected_question_ids = list(question_ids or [])
            BankQuestionValidator.validate_unique_question_ids(selected_question_ids)
            existing_links = await self.repository.get_questions_in_bank_by_ids(
                source_bank_id, selected_question_ids
            )
            BankQuestionValidator.validate_questions_linked_to_bank(
                existing_links,
                source_bank_id,
                selected_question_ids,
            )
            source_questions = (
                await self.repository.get_question_entities_in_bank_by_ids(
                    source_bank_id,
                    selected_question_ids,
                )
            )

        if not source_questions:
            return 0

        cloned_questions = [
            deep_copy_question_for_clone(question, user_id)
            for question in source_questions
        ]
        created_questions = await self.question_repo.bulk_create_questions(
            cloned_questions
        )
        await self.repository.add_questions_to_bank(
            target_bank_id,
            [question.id for question in created_questions],
            user_id,
        )
        return len(created_questions)

    @cache_delete(
        key_builder=lambda self,
        bank_id,
        *args,
        **kwargs: self._get_bank_question_cache_keys(bank_id)
    )
    async def remove_questions_from_bank(
        self, bank_id: UUID, question_ids: List[UUID], user_id: UUID
    ) -> None:
        """Unlink existing questions from a bank.

        Args:
            bank_id: Target bank ID.
            question_ids: Question IDs to remove from the bank.
            user_id: Authenticated user performing the operation.

        Raises:
            BankNotFoundError: If bank does not exist.
            BankAccessDeniedError: If user cannot edit the bank.
            BankQuestionNotFoundError: If link does not exist.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        self.validator.check_edit_bank(user_id=user_id, bank=bank)

        existing = await self.repository.get_questions_in_bank_by_ids(
            bank_id, question_ids
        )
        BankQuestionValidator.validate_questions_linked_to_bank(
            existing, bank_id, question_ids
        )

        await self.repository.remove_questions_from_bank(existing)

    @cache_get(
        key_builder=lambda self,
        bank_id,
        user_id,
        skip=0,
        limit=100,
        filters=None: f"banks:questions:v2:{bank_id}:user:{user_id}:skip:{skip}:limit:{limit}:filters:{hash(str(filters))}",
        ttl=300,
    )
    async def get_bank_questions(
        self,
        bank_id: UUID,
        user_id: UUID,
        skip: int = 0,
        limit: int = 100,
        filters: BankQuestionFilters | None = None,
    ) -> tuple[int, List[BankQuestionMetadataResponse]]:
        """Return paginated question summaries for a bank.

        Args:
            bank_id: Target bank ID.
            user_id: Authenticated user requesting data.
            skip: Pagination offset.
            limit: Pagination page size.

        Returns:
            Tuple of total count and question summary list.

        Raises:
            BankNotFoundError: If bank does not exist.
            BankAccessDeniedError: If user cannot read the bank.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        self.validator.check_read_bank(user_id=user_id, bank=bank)

        pagination = PaginationParams(skip=skip, limit=limit)
        result = await self.repository.get_questions_in_bank(bank_id, pagination, filters)

        responses = to_bank_question_metadata_responses(result.items)
        return result.total, responses

    @cache_get(
        key_builder=lambda self,
        bank_id,
        question_id,
        user_id: f"bank:question:v2:{bank_id}:{question_id}:user:{user_id}",
        ttl=300,
    )
    async def get_bank_question(
        self, bank_id: UUID, question_id: UUID, user_id: UUID
    ) -> QuestionResponse:
        """Return hydrated question details inside a bank scope.

        Args:
            bank_id: Target bank ID.
            question_id: Target question ID.
            user_id: Authenticated user requesting data.

        Returns:
            Hydrated question response with template code resolved from storage.

        Raises:
            BankNotFoundError: If bank does not exist.
            BankAccessDeniedError: If user cannot read the bank.
            BankQuestionNotFoundError: If question is not linked to the bank.
            QuestionNotFoundError: If question no longer exists.
            CodeStorageError: If template code retrieval fails.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        self.validator.check_read_bank(user_id=user_id, bank=bank)

        existing = await self.repository.get_questions_in_bank_by_ids(
            bank_id, [question_id]
        )
        if not existing:
            raise BankQuestionNotFoundError(str(bank_id), str(question_id))

        question = await self.question_repo.get_question_or_raise(question_id)
        response = to_bank_question_response(question)
        return await self._hydrate_question_template_codes(response)



    @cache_delete(
        key_builder=lambda self, bank_id, question_id, *args, **kwargs: [
            f"question:{question_id}",
            f"question:{question_id}:*",
            f"bank:question:{bank_id}:{question_id}:*",
            f"bank:question:*:{question_id}:*",
            "banks:questions:*",
        ]
    )
    async def update_bank_question(
        self,
        bank_id: UUID,
        question_id: UUID,
        update_data: QuestionUpdate,
        user_id: UUID,
    ) -> QuestionResponse:
        """Perform an atomic, comprehensive update of a bank question.

        Handles metadata (title, difficulty), limits, tags, allowed languages,
        starter code templates, and test cases in a single operation.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        self.validator.check_edit_bank(user_id=user_id, bank=bank)

        existing = await self.repository.get_questions_in_bank_by_ids(
            bank_id, [question_id]
        )
        if not existing:
            raise BankQuestionNotFoundError(str(bank_id), str(question_id))

        question = await self.question_repo.get_question_or_raise(question_id)

        # Validation
        if update_data.testcases is not None:
            QuestionValidator.validate_testcases_format(update_data.testcases)
        QuestionValidator.validate_limits(
            update_data.time_limit_ms, update_data.memory_limit_mb
        )
        if update_data.allowed_languages is not None:
            QuestionValidator.validate_allowed_languages(update_data.allowed_languages)
        if update_data.templates is not None:
            QuestionValidator.validate_unique_template_language_ids(
                [template.language_id for template in update_data.templates]
            )

        await QuestionValidator.validate_platform_languages_exist(
            self.language_repo,
            allowed_language_ids=update_data.allowed_languages or [],
            template_language_ids=[
                t.language_id for t in (update_data.templates or [])
            ],
        )

        # Build DTOs
        testcase_dtos = build_update_testcase_dtos(update_data.testcases)

        template_dtos: list[CreateQuestionTemplateData] | None = None
        if update_data.templates is not None:
            template_dtos = []
            for template in update_data.templates:
                template_id = uuid.uuid4() if not hasattr(template, "id") or not template.id else template.id
                mapped_template_dto = build_template_dto(
                    template_id=template_id,
                    template=template,
                    solution_code_value=template.solution_code,
                )
                template_dtos.append(mapped_template_dto)

        update_dto = build_update_question_dto(
            update_data,
            testcase_dtos=testcase_dtos,
            template_dtos=template_dtos,
        )

        # Apply and persist
        apply_question_updates(question, update_dto)
        updated_question = await self.question_repo.update_question(question)

        response = to_bank_question_response(updated_question)
        return await self._hydrate_question_template_codes(response)
