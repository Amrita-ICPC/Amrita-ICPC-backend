from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ContestQuestion, Question
from app.models.question import Submission


class StudentContestQuestionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_contest_questions(self, contest_id: UUID) -> list[ContestQuestion]:
        """
        Retrieve all ContestQuestion records for a contest, ordered by order.
        """
        query = (
            select(ContestQuestion)
            .where(ContestQuestion.contest_id == contest_id)
            .order_by(ContestQuestion.order.asc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_contest_question_details(
        self, contest_id: UUID, question_id: UUID
    ) -> Question | None:
        """
        Retrieve details of a specific question in a contest, with all necessary
        relationships loaded (languages, templates, tags, testcases).
        """
        from app.models.question import QuestionLanguage, QuestionTemplate
        from app.models.tag import QuestionTag

        # Verify the question is in the contest first
        in_contest_stmt = select(ContestQuestion).where(
            ContestQuestion.contest_id == contest_id,
            ContestQuestion.question_id == question_id,
        )
        in_contest_res = await self.db.execute(in_contest_stmt)
        if not in_contest_res.scalars().first():
            return None

        # Fetch the question with relationships
        stmt = (
            select(Question)
            .where(Question.id == question_id)
            .options(
                selectinload(Question.languages).joinedload(QuestionLanguage.language),
                selectinload(Question.tags).joinedload(QuestionTag.tag),
                selectinload(Question.templates).joinedload(QuestionTemplate.language),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_submissions_by_team_and_question(
        self, contest_team_id: UUID, question_id: UUID
    ) -> list[Submission]:
        """
        Retrieve all submissions for a question made by a contest team,
        ordered by submission time descending.
        """
        from app.models.contest import ContestSubmission

        stmt = (
            select(Submission)
            .join(ContestSubmission, ContestSubmission.submission_id == Submission.id)
            .where(
                ContestSubmission.contest_team_id == contest_team_id,
                Submission.question_id == question_id,
            )
            .order_by(Submission.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
