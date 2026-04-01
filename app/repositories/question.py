from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.question import QuestionNotFoundError
from app.models.bank import Bank, BankQuestion, BankShare
from app.models.contest import Contest, ContestInstructor, ContestQuestion, ContestTeam
from app.models.question import Question
from app.models.team import TeamUser
from app.repositories.dto.question import CreateQuestionData, UpdateQuestionData


class QuestionRepository:
    """Repository for question-related database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_question_or_raise(self, question_id: UUID) -> Question:
        """
        Retrieve a question by its ID or raise an exception if not found.

        Args:
            question_id: ID of the question to retrieve.

        Returns:
            The Question object if found.

        Raises:
            QuestionNotFoundError: If the question with the given ID does not exist.
        """
        result = await self.db.execute(
            select(Question).filter(Question.id == question_id)
        )
        question = result.scalars().first()
        if not question:
            raise QuestionNotFoundError(str(question_id))
        return question

    async def create_question(self, data: CreateQuestionData) -> Question:
        """
        Create a new question in the database.

        Args:
            data: CreateQuestionData object containing all question creation data.

        Returns:
            The created Question object with ID and timestamps populated.
        """
        db_question = Question(
            question_text=data.question_text,
            difficulty=data.difficulty,
            allowed_languages=data.allowed_languages,
            testcases=data.testcases,
            time_limit_ms=data.time_limit_ms,
            memory_limit_mb=data.memory_limit_mb,
            created_by=data.created_by,
        )
        self.db.add(db_question)
        await self.db.flush()
        await self.db.refresh(db_question)
        return db_question

    async def update_question(
        self, question: Question, update_data: UpdateQuestionData
    ) -> Question:
        """
        Update an existing question in the database.

        Args:
            question: Question object to update.
            update_data: UpdateQuestionData object with fields to update.

        Returns:
            The updated Question object.
        """
        update_dict = update_data.__dict__
        for field, value in update_dict.items():
            if value is not None:
                setattr(question, field, value)

        await self.db.flush()
        await self.db.refresh(question)
        return question

    async def delete_question(self, question: Question) -> None:
        """
        Delete a question from the database.

        Args:
            question: Question object to delete.
        """
        await self.db.delete(question)
        await self.db.flush()

    async def user_has_access_to_question_via_bank(
        self, user_id: UUID, question_id: UUID
    ) -> bool:
        result = await self.db.execute(
            select(BankQuestion)
            .join(Bank, Bank.id == BankQuestion.bank_id)
            .outerjoin(BankShare, BankShare.bank_id == Bank.id)
            .filter(
                BankQuestion.question_id == question_id,
                or_(Bank.created_by == user_id, BankShare.user_id == user_id),
            )
        )
        return result.scalars().first() is not None

    async def user_has_access_to_question_via_contest(
        self, user_id: UUID, question_id: UUID
    ) -> bool:
        result = await self.db.execute(
            select(ContestQuestion)
            .join(Contest, Contest.id == ContestQuestion.contest_id)
            .outerjoin(ContestInstructor, ContestInstructor.contest_id == Contest.id)
            .outerjoin(ContestTeam, ContestTeam.contest_id == Contest.id)
            .outerjoin(TeamUser, TeamUser.team_id == ContestTeam.team_id)
            .filter(
                ContestQuestion.question_id == question_id,
                or_(
                    Contest.created_by == user_id,
                    ContestInstructor.instructor_id == user_id,
                    TeamUser.user_id == user_id,
                    Contest.is_public.is_(True),
                ),
            )
        )
        return result.scalars().first() is not None
