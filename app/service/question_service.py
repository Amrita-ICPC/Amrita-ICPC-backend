from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get
from app.core.guards.question import QuestionOperationGuard
from app.repositories.dto.question import CreateQuestionData, UpdateQuestionData
from app.repositories.question import QuestionRepository
from app.schema.question import QuestionCreate, QuestionResponse, QuestionUpdate
from app.validators.question import QuestionValidator


class QuestionService:
    """Service layer for question management.

    Orchestrates business logic between repository, validator, and guard layers.
    Returns Pydantic DTOs for the router layer.
    """

    def __init__(
        self,
        repository: QuestionRepository,
        guard: QuestionOperationGuard,
        validator: QuestionValidator,
    ):
        self.repository = repository
        self.guard = guard
        self.validator = validator

    def _get_question_cache_keys(self, question_id: UUID) -> list[str]:
        return [f"question:{question_id}", f"question:{question_id}:*"]

    async def create_question(
        self, question_data: QuestionCreate, user_id: UUID
    ) -> QuestionResponse:
        """Create a new question."""
        self.validator.validate_testcases_format(question_data.testcases)
        self.validator.validate_limits(
            question_data.time_limit_ms, question_data.memory_limit_mb
        )
        self.validator.validate_allowed_languages(question_data.allowed_languages)

        create_dto = CreateQuestionData(
            question_text=question_data.question_text,
            difficulty=question_data.difficulty,
            allowed_languages=question_data.allowed_languages,
            testcases=question_data.testcases,
            time_limit_ms=question_data.time_limit_ms,
            memory_limit_mb=question_data.memory_limit_mb,
            created_by=user_id,
        )

        question = await self.repository.create_question(create_dto)
        return QuestionResponse.model_validate(question)

    @cache_get(
        key_builder=lambda self,
        question_id,
        user_id: f"question:{question_id}:user:{user_id}",
        ttl=300,
    )
    async def get_question_by_id(
        self, question_id: UUID, user_id: UUID
    ) -> QuestionResponse:
        """Retrieve a question by ID, checking access permissions."""
        question = await self.repository.get_question_or_raise(question_id)
        await self.guard.check_read_question(user_id=user_id, question=question)
        return QuestionResponse.model_validate(question)

    @cache_delete(
        key_builder=lambda self,
        question_id,
        *args,
        **kwargs: self._get_question_cache_keys(question_id)
    )
    async def update_question(
        self, question_id: UUID, update_data: QuestionUpdate, user_id: UUID
    ) -> QuestionResponse:
        """Update a question and invalidate the cache."""
        question = await self.repository.get_question_or_raise(question_id)
        await self.guard.check_manage_question(user_id=user_id, question=question)

        if update_data.testcases is not None:
            self.validator.validate_testcases_format(update_data.testcases)
        self.validator.validate_limits(
            update_data.time_limit_ms, update_data.memory_limit_mb
        )
        if update_data.allowed_languages is not None:
            self.validator.validate_allowed_languages(update_data.allowed_languages)

        update_dto = UpdateQuestionData(
            question_text=update_data.question_text,
            difficulty=update_data.difficulty,
            allowed_languages=update_data.allowed_languages,
            testcases=update_data.testcases,
            time_limit_ms=update_data.time_limit_ms,
            memory_limit_mb=update_data.memory_limit_mb,
        )

        updated_question = await self.repository.update_question(question, update_dto)
        return QuestionResponse.model_validate(updated_question)

    @cache_delete(
        key_builder=lambda self,
        question_id,
        *args,
        **kwargs: self._get_question_cache_keys(question_id)
    )
    async def delete_question(self, question_id: UUID, user_id: UUID) -> None:
        """Delete a question and invalidate the cache."""
        question = await self.repository.get_question_or_raise(question_id)
        await self.guard.check_manage_question(user_id=user_id, question=question)
        await self.repository.delete_question(question)
