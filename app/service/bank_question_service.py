from typing import List
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get
from app.exceptions.bank import (
    BankQuestionAlreadyExistsError,
    BankQuestionNotFoundError,
)
from app.repositories.bank import BankRepository
from app.repositories.dto.pagination import PaginationParams
from app.repositories.question import QuestionRepository
from app.schema.question import QuestionListSummaryResponse, QuestionResponse
from app.validators.bank import BankValidator


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

        for q_id in question_ids:
            await self.question_repo.get_question_or_raise(q_id)

        existing = await self.repository.get_questions_in_bank_by_ids(
            bank_id, question_ids
        )
        if existing:
            raise BankQuestionAlreadyExistsError(
                str(bank_id), str(existing[0].question_id)
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
        existing_ids = {bq.question_id for bq in existing}

        missing = [q_id for q_id in question_ids if q_id not in existing_ids]
        if missing:
            raise BankQuestionNotFoundError(str(bank_id), str(missing[0]))

        await self.repository.remove_questions_from_bank(existing)

    @cache_get(
        key_builder=lambda self,
        bank_id,
        user_id,
        skip=0,
        limit=100: f"banks:questions:{bank_id}:skip:{skip}:limit:{limit}",
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
