import asyncio
from typing import List
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get
from app.core.storage import CodeStorageService
from app.exceptions.bank import (
    BankQuestionNotFoundError,
)
from app.exceptions.question import CodeStorageError
from app.repositories.bank import BankRepository
from app.repositories.dto.pagination import PaginationParams
from app.repositories.question import QuestionRepository
from app.schema.question import QuestionListSummaryResponse, QuestionResponse
from app.validators.bank import BankValidator
from app.validators.bank_question import BankQuestionValidator


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

    def _get_bank_question_cache_keys(self, bank_id: UUID) -> list[str]:
        """Build cache keys and patterns for bank-question invalidation.

        Args:
            bank_id: Target bank ID.

        Returns:
            List of key patterns affected by association mutations.
        """
        return [
            f"bank:{bank_id}",
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
        limit=100: f"banks:questions:v2:{bank_id}:user:{user_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_bank_questions(
        self, bank_id: UUID, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[int, List[QuestionListSummaryResponse]]:
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
        result = await self.repository.get_questions_in_bank(bank_id, pagination)

        responses = [QuestionListSummaryResponse.from_question(q) for q in result.items]
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
        response = QuestionResponse.from_question(question)
        return await self._hydrate_question_template_codes(response)
