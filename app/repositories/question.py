from typing import cast
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions.question import QuestionNotFoundError
from app.models.bank import Bank, BankQuestion, BankShare
from app.models.contest import Contest, ContestInstructor, ContestQuestion, ContestTeam
from app.models.question import Question, QuestionLanguage, QuestionTemplate
from app.models.team import TeamUser


class QuestionRepository:
    """Repository for question-related database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _question_with_relations_query():
        return select(Question).options(
            selectinload(Question.languages).selectinload(QuestionLanguage.language),
            selectinload(Question.tags),
            selectinload(Question.testcases),
            selectinload(Question.templates).selectinload(QuestionTemplate.language),
        )

    @staticmethod
    def _question_with_relations_by_id_query(question_id: UUID):
        return QuestionRepository._question_with_relations_query().where(
            Question.id == question_id
        )

    async def _fetch_question_or_raise(self, question_id: UUID) -> Question:
        """Fetch a single question with relations or raise if missing."""
        result = await self.db.execute(
            self._question_with_relations_by_id_query(question_id)
        )
        question = result.scalars().one_or_none()
        if question is None:
            raise QuestionNotFoundError(str(question_id))
        return cast(Question, question)

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
        return await self._fetch_question_or_raise(question_id)

    async def validate_questions_exist(self, question_ids: list[UUID]) -> None:
        """Validate that all provided question IDs exist.

        Args:
            question_ids: List of question IDs to validate.

        Raises:
            QuestionNotFoundError: If any question ID does not exist.
        """
        if not question_ids:
            return

        unique_ids = set(question_ids)
        result = await self.db.execute(
            select(Question.id).where(Question.id.in_(unique_ids))
        )
        found_ids = set(result.scalars().all())
        if len(found_ids) != len(unique_ids):
            missing_id = next(iter(unique_ids - found_ids))
            raise QuestionNotFoundError(str(missing_id))

    async def create_question(self, question: Question) -> Question:
        """
        Create a new question in the database.

        Args:
            data: CreateQuestionData object containing all question creation data.

        Returns:
            The created Question object with ID and timestamps populated.
        """
        self.db.add(question)
        await self.db.flush()
        return await self._fetch_question_or_raise(question.id)

    async def bulk_create_questions(self, questions: list[Question]) -> list[Question]:
        """
        Create multiple questions in the database.

        Args:
            question_data_list: List of CreateQuestionData objects containing question
                creation data.

        Returns:
            List of created Question objects with IDs and timestamps populated.
        """
        if not questions:
            return []

        self.db.add_all(questions)
        await self.db.flush()
        return questions

    async def update_question(self, question: Question) -> Question:
        """
        Update an existing question in the database.

        Args:
            question: Question object to update.
            update_data: UpdateQuestionData object with fields to update.

        Returns:
            The updated Question object.
        """
        await self.db.flush()
        return await self._fetch_question_or_raise(question.id)

    async def delete_question(self, question: Question) -> None:
        """
        Delete a question from the database.

        Args:
            question: Question object to delete.
        """
        await self.db.delete(question)
        await self.db.flush()

    async def rollback(self) -> None:
        """Rollback the active transaction."""
        await self.db.rollback()

    async def user_has_access_to_question_via_bank(
        self, user_id: UUID, question_id: UUID
    ) -> bool:
        result = await self.db.execute(
            select(BankQuestion.question_id)
            .join(Bank, Bank.id == BankQuestion.bank_id)
            .outerjoin(BankShare, BankShare.bank_id == Bank.id)
            .where(
                BankQuestion.question_id == question_id,
                or_(Bank.created_by == user_id, BankShare.user_id == user_id),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def user_has_access_to_question_via_contest(
        self, user_id: UUID, question_id: UUID
    ) -> bool:
        result = await self.db.execute(
            select(ContestQuestion.question_id)
            .join(Contest, Contest.id == ContestQuestion.contest_id)
            .outerjoin(ContestInstructor, ContestInstructor.contest_id == Contest.id)
            .outerjoin(ContestTeam, ContestTeam.contest_id == Contest.id)
            .outerjoin(TeamUser, TeamUser.team_id == ContestTeam.team_id)
            .where(
                ContestQuestion.question_id == question_id,
                or_(
                    Contest.created_by == user_id,
                    ContestInstructor.instructor_id == user_id,
                    TeamUser.user_id == user_id,
                    Contest.is_public.is_(True),
                ),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
