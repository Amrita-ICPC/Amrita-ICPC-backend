from typing import cast
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions.question import QuestionNotFoundError
from app.models.bank import Bank, BankQuestion, BankShare
from app.models.contest import (
    Contest,
    ContestInstructor,
    ContestQuestion,
    ContestSubmission,
    ContestTeam,
)
from app.models.question import Question, QuestionLanguage, QuestionTemplate, Submission
from app.models.tag import QuestionTag
from app.models.team import TeamUser
from app.repositories.dto.evaluation import EvaluationResult


class QuestionRepository:
    """Repository for question-related database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _question_with_relations_query():
        return select(Question).options(
            selectinload(Question.languages).selectinload(QuestionLanguage.language),
            selectinload(Question.tags).selectinload(QuestionTag.tag),
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
            question: Question ORM object to persist.

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
            questions: List of Question ORM objects to persist.

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
        Persist updates to an existing question in the database.

        Args:
            question: Question ORM object with updated fields.

        Returns:
            The updated Question object with relations loaded.
        """
        await self.db.flush()
        return await self._fetch_question_or_raise(question.id)

    async def delete_question(self, question_id: UUID) -> None:
        """
        Delete a question from the database.

        Deletes the question and all related records via ORM cascade semantics.
        This ensures proper handling of cascading deletes for related entities
        like testcases, templates, and language assignments.

        Args:
            question_id: ID of the question to delete.

        Raises:
            QuestionNotFoundError: If question does not exist.
        """
        question = await self._fetch_question_or_raise(question_id)
        await self.db.delete(question)
        await self.db.flush()

    async def rollback(self) -> None:
        """Rollback the active transaction."""
        await self.db.rollback()

    async def user_has_access_to_question_via_bank(
        self, user_id: UUID, question_id: UUID
    ) -> bool:
        """
        Check if user has access to a question through a bank.

        User has access if they are the bank owner or have a share.

        Args:
            user_id: ID of the user to check.
            question_id: ID of the question.

        Returns:
            True if user has access via bank, False otherwise.
        """
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
        """
        Check if user has access to a question through a contest.

        User has access if they created the contest, are an instructor,
        are on a participating team, or contest is public.

        Args:
            user_id: ID of the user to check.
            question_id: ID of the question.

        Returns:
            True if user has access via contest, False otherwise.
        """
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

    async def add_templates_to_question(
        self, question_id: UUID, templates: list[QuestionTemplate]
    ) -> None:
        """Add multiple templates to an existing question.

        Args:
            question_id: ID of the question to add templates to.
            templates: List of QuestionTemplate objects to persist.

        Raises:
            QuestionNotFoundError: If the question does not exist.
        """
        await self._fetch_question_or_raise(question_id)
        for template in templates:
            template.question_id = question_id
            self.db.add(template)
        await self.db.flush()

    async def get_question_templates(self, question_id: UUID) -> list[QuestionTemplate]:
        """Get all templates for a question.

        Args:
            question_id: ID of the question.

        Returns:
            List of QuestionTemplate objects for the question.
        """
        result = await self.db.execute(
            select(QuestionTemplate)
            .where(QuestionTemplate.question_id == question_id)
            .options(selectinload(QuestionTemplate.language))
        )
        return cast(list[QuestionTemplate], result.scalars().all())

    async def create_submission(
        self,
        submission: Submission,
        contest_submission: ContestSubmission | None = None,
    ) -> Submission:
        """
        Create a new submission and link it to a contest if provided.

        Args:
            submission: The Submission ORM object to persist.
            contest_submission: Optional ContestSubmission ORM object to associate with the submission.

        Returns:
            Submission: The persisted submission object.
        """
        self.db.add(submission)
        if contest_submission:
            self.db.add(contest_submission)
        await self.db.flush()
        return submission

    async def get_submission(self, submission_id: UUID) -> Submission | None:
        """
        Retrieve a submission by its ID.

        Args:
            submission_id: ID of the submission to retrieve.

        Returns:
            The Submission object if found, otherwise None.
        """
        result = await self.db.execute(
            select(Submission)
            .options(
                selectinload(Submission.contest_submission).selectinload(
                    ContestSubmission.contest_team
                ),
                selectinload(Submission.testcases),
            )
            .where(Submission.id == submission_id)
        )
        return result.scalar_one_or_none()

    async def get_contest_question_score(
        self, contest_id: UUID, question_id: UUID
    ) -> int | None:
        """
        Get the configured score for a question within a contest.

        Args:
            contest_id: ID of the contest.
            question_id: ID of the question.

        Returns:
            The score of the question in the contest, or None if not found.
        """
        result = await self.db.execute(
            select(ContestQuestion.score).where(
                ContestQuestion.contest_id == contest_id,
                ContestQuestion.question_id == question_id,
            )
        )
        return result.scalar_one_or_none()

    async def complete_submission(
        self, submission: Submission, result: EvaluationResult
    ) -> None:
        """Complete a submission with the evaluation result."""
        submission.is_evaluated = True
        submission.total_time = result.total_time
        submission.total_memory = result.total_memory

        self.db.add_all(result.testcase_results)
        await self.db.flush()
