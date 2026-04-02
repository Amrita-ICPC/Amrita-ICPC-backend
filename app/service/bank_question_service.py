import copy
from typing import List
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get
from app.exceptions.bank import (
    BankQuestionNotFoundError,
)
from app.exceptions.question import QuestionNotFoundError
from app.repositories.bank import BankRepository
from app.repositories.dto.pagination import PaginationParams
from app.repositories.dto.question import CreateQuestionData
from app.repositories.question import QuestionRepository
from app.schema.question import QuestionListSummaryResponse, QuestionResponse
from app.validators.bank import BankValidator
from app.validators.bank_question import BankQuestionValidator


class BankQuestionService:
    """Service layer coordinating bank-question operations through injected repositories and guards."""

    def __init__(
        self,
        repository: BankRepository,
        question_repo: QuestionRepository,
        validator: BankValidator,
    ):
        """Initialize the bank question service layer dependencies.

        Args:
            repository (BankRepository): Data access gateway.
            question_repo (QuestionRepository): Question isolation gateway.
            validator (BankValidator): Schema and logic validation.
        """
        self.repository = repository
        self.question_repo = question_repo
        self.validator = validator

    @cache_delete(
        key_builder=lambda self, bank_id, *args, **kwargs: [
            f"bank:{bank_id}",
            f"banks:questions:{bank_id}:*",
        ]
    )
    async def add_questions_to_bank(
        self, bank_id: UUID, question_ids: List[UUID], user_id: UUID
    ) -> None:
        """
        Link multiple existing questions to a specific bank.

        Args:
            bank_id: UUID of the target bank.
            question_ids: List of question UUIDs to securely link.
            user_id: UUID of the editing user initiating the link.

        Raises:
            BankNotFoundError: If the bank does not exist.
            BankAccessDeniedError: If the user lacks permission to edit the bank.
            BankQuestionAlreadyExistsError: If any of the questions are already linked.
            QuestionNotFoundError: If any provided question ID does not exist natively.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        self.validator.check_edit_bank(user_id=user_id, bank=bank)

        await self.question_repo.validate_questions_exist(question_ids)

        existing = await self.repository.get_questions_in_bank_by_ids(
            bank_id, question_ids
        )
        BankQuestionValidator.validate_question_already_exist(
            existing, bank_id, question_ids
        )

        await self.repository.add_questions_to_bank(bank_id, question_ids, user_id)

    @cache_delete(
        key_builder=lambda self, bank_id, *args, **kwargs: [
            f"bank:{bank_id}",
            f"banks:questions:{bank_id}:*",
        ]
    )
    async def remove_questions_from_bank(
        self, bank_id: UUID, question_ids: List[UUID], user_id: UUID
    ) -> None:
        """
        Remove multiple linked questions from a specific bank.

        Args:
            bank_id: UUID of the target bank.
            question_ids: List of question UUIDs to disconnect from the bank.
            user_id: UUID of the editing user initiating the removal.

        Raises:
            BankNotFoundError: If the bank does not exist.
            BankAccessDeniedError: If the user lacks permission to edit the bank.
            BankQuestionNotFoundError: If any provided question ID is not linked to the bank.
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
        limit=100: f"banks:questions:{bank_id}:user:{user_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_bank_questions(
        self, bank_id: UUID, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[int, List[QuestionListSummaryResponse]]:
        """
        Retrieve a paginated summary list of questions associated with a bank.

        Args:
            bank_id: UUID of the target bank.
            user_id: UUID of the reading user initiating the fetch.
            skip: Number of questions to skip for offset.
            limit: Maximum subset of questions to return.

        Returns:
            A tuple containing the total count of questions linked and the subset list of QuestionListSummaryResponse objects.

        Raises:
            BankNotFoundError: If the target bank does not exist.
            BankAccessDeniedError: If the user lacks permission to read the bank configurations.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        self.validator.check_read_bank(user_id=user_id, bank=bank)

        pagination = PaginationParams(skip=skip, limit=limit)
        result = await self.repository.get_questions_in_bank(bank_id, pagination)

        responses = [
            QuestionListSummaryResponse.model_validate(q) for q in result.items
        ]
        return result.total, responses

    async def get_bank_question(
        self, bank_id: UUID, question_id: UUID, user_id: UUID
    ) -> QuestionResponse:
        """
        Retrieve detailed information of a specific question inside a bank.

        Args:
            bank_id: UUID of the target bank.
            question_id: UUID of the target detailed question definition.
            user_id: UUID of the reading user initiating the fetch.

        Returns:
            QuestionResponse: The complete question definition containing test evaluations and limits.

        Raises:
            BankNotFoundError: If the target bank does not exist natively.
            BankAccessDeniedError: If the user lacks permission to read the bank dependencies.
            BankQuestionNotFoundError: If the specific question isn't structurally linked to the bank context.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        self.validator.check_read_bank(user_id=user_id, bank=bank)

        existing = await self.repository.get_questions_in_bank_by_ids(
            bank_id, [question_id]
        )
        if not existing:
            raise BankQuestionNotFoundError(str(bank_id), str(question_id))

        question = await self.question_repo.get_question_or_raise(question_id)
        return QuestionResponse.model_validate(question)

    @cache_delete(
        key_builder=lambda self, source_bank_id, target_bank_id, *args, **kwargs: [
            f"bank:{source_bank_id}",
            f"bank:{target_bank_id}",
            f"banks:questions:{source_bank_id}:*",
            f"banks:questions:{target_bank_id}:*",
        ]
    )
    async def clone_questions_to_bank(
        self,
        source_bank_id: UUID,
        target_bank_id: UUID,
        user_id: UUID,
        question_ids: List[UUID] | None = None,
        copy_all: bool = False,
    ) -> int:
        """
        Clone questions from one bank to another.

        Args:
            source_bank_id: UUID of the bank to clone questions from.
            target_bank_id: UUID of the bank to clone questions to.
            user_id: UUID of the editing user initiating the clone.
            question_ids: Optional list of specific question UUIDs to copy.
            copy_all: If True, all questions from the source bank are copied.

        Returns:
            int: Number of questions copied into the target bank.

        Raises:
            BankNotFoundError: If either the source or target bank does not exist.
            BankAccessDeniedError: If the user lacks permission to edit either bank.
            BankQuestionAlreadyExistsError: If any of the questions to be copied already exist in the target bank.
            QuestionNotFoundError: If any provided question ID does not exist in the source bank.
        """
        source_bank = await self.repository.get_bank_or_raise(
            source_bank_id, load_relations=True
        )
        target_bank = await self.repository.get_bank_or_raise(
            target_bank_id, load_relations=True
        )

        self.validator.check_read_bank(user_id=user_id, bank=source_bank)
        self.validator.check_edit_bank(user_id=user_id, bank=target_bank)

        BankQuestionValidator.validate_clone_questions(
            source_bank_id, target_bank_id, question_ids, copy_all
        )

        if copy_all:
            questions = await self.repository.get_all_question_entities_in_bank(
                source_bank_id
            )
        else:
            questions = await self.repository.get_question_entities_in_bank_by_ids(
                source_bank_id, question_ids or []
            )
            if question_ids is None:
                questions = []
            elif len(questions) != len(question_ids):
                raise QuestionNotFoundError(
                    "One or more questions to clone were not found in the source bank."
                )

        new_questions = [
            CreateQuestionData(
                question_text=question_data.question_text,
                difficulty=question_data.difficulty,
                allowed_languages=copy.deepcopy(question_data.allowed_languages),
                testcases=copy.deepcopy(question_data.testcases),
                time_limit_ms=question_data.time_limit_ms,
                memory_limit_mb=question_data.memory_limit_mb,
                created_by=user_id,
            )
            for question_data in questions
        ]

        created_questions = await self.question_repo.bulk_create_questions(
            new_questions
        )
        new_ids = [question.id for question in created_questions]
        await self.repository.add_questions_to_bank(
            target_bank_id,
            new_ids,
            user_id,
        )

        return len(created_questions)
