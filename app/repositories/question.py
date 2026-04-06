from typing import cast
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions.question import QuestionNotFoundError
from app.models.bank import Bank, BankQuestion, BankShare
from app.models.contest import Contest, ContestInstructor, ContestQuestion, ContestTeam
from app.models.question import Question, QuestionLanguage, QuestionTemplate, TestCase
from app.models.tag import QuestionTag
from app.models.team import TeamUser
from app.repositories.dto.question import CreateQuestionData, UpdateQuestionData


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

    async def create_question(self, data: CreateQuestionData) -> Question:
        """
        Create a new question in the database.

        Args:
            data: CreateQuestionData object containing all question creation data.

        Returns:
            The created Question object with ID and timestamps populated.
        """
        db_question = Question(
            id=data.id,
            question_text=data.question_text,
            difficulty=data.difficulty,
            time_limit_ms=data.time_limit_ms,
            memory_limit_mb=data.memory_limit_mb,
            created_by=data.created_by,
            languages=[
                QuestionLanguage(language_id=language_id)
                for language_id in data.allowed_language_ids
            ],
            tags=[QuestionTag(tag_id=tag_id) for tag_id in data.tag_ids],
            testcases=[
                TestCase(
                    input=testcase.input,
                    output=testcase.output,
                    is_hidden=testcase.is_hidden,
                    weight=testcase.weight,
                    order=testcase.order,
                    created_by=data.created_by,
                )
                for testcase in data.testcases
            ],
            templates=[
                QuestionTemplate(
                    id=template.id,
                    language_id=template.language_id,
                    starter_code=template.starter_code,
                    driver_code=template.driver_code,
                    solution_code=template.solution_code,
                )
                for template in data.templates
            ],
        )
        self.db.add(db_question)
        await self.db.flush()
        return await self._fetch_question_or_raise(db_question.id)

    async def bulk_create_questions(
        self, question_data_list: list[CreateQuestionData]
    ) -> list[Question]:
        """
        Create multiple questions in the database.

        Args:
            question_data_list: List of CreateQuestionData objects containing question
                creation data.

        Returns:
            List of created Question objects with IDs and timestamps populated.
        """
        if not question_data_list:
            return []

        db_questions = [
            Question(
                id=data.id,
                question_text=data.question_text,
                difficulty=data.difficulty,
                time_limit_ms=data.time_limit_ms,
                memory_limit_mb=data.memory_limit_mb,
                created_by=data.created_by,
                languages=[
                    QuestionLanguage(language_id=language_id)
                    for language_id in data.allowed_language_ids
                ],
                tags=[QuestionTag(tag_id=tag_id) for tag_id in data.tag_ids],
                testcases=[
                    TestCase(
                        input=testcase.input,
                        output=testcase.output,
                        is_hidden=testcase.is_hidden,
                        weight=testcase.weight,
                        order=testcase.order,
                        created_by=data.created_by,
                    )
                    for testcase in data.testcases
                ],
                templates=[
                    QuestionTemplate(
                        id=template.id,
                        language_id=template.language_id,
                        starter_code=template.starter_code,
                        driver_code=template.driver_code,
                        solution_code=template.solution_code,
                    )
                    for template in data.templates
                ],
            )
            for data in question_data_list
        ]

        self.db.add_all(db_questions)
        await self.db.flush()
        return db_questions

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
                if field == "allowed_languages":
                    question.languages = [
                        QuestionLanguage(language_id=language_id)
                        for language_id in value
                    ]
                    continue
                if field == "testcases":
                    question.testcases = [
                        TestCase(
                            input=testcase.input,
                            output=testcase.output,
                            is_hidden=testcase.is_hidden,
                            weight=testcase.weight,
                            order=testcase.order,
                            created_by=question.created_by,
                        )
                        for testcase in value
                    ]
                    continue
                if field == "tag_ids":
                    question.tags = [QuestionTag(tag_id=tag_id) for tag_id in value]
                    continue
                if field == "templates":
                    question.templates = [
                        QuestionTemplate(
                            id=template.id,
                            language_id=template.language_id,
                            starter_code=template.starter_code,
                            driver_code=template.driver_code,
                            solution_code=template.solution_code,
                        )
                        for template in value
                    ]
                    continue
                setattr(question, field, value)

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
