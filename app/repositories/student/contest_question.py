from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ContestQuestion, Question
from app.models.question import Submission
from app.utils.enums import SubmissionStatus


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

    async def get_question_attempt_status(
        self, contest_id: UUID, contest_team_id: UUID
    ) -> dict[UUID, bool]:
        """
        For every question the team has submitted at least once in this
        contest, compute whether it's solved (has at least one submission
        where every testcase passed).

        A question absent from the returned dict has zero submissions from
        this team, i.e. not attempted.

        Args:
            contest_id: The contest to scope submissions to.
            contest_team_id: The team whose submissions to check.

        Returns:
            dict mapping question_id -> solved (True if any submission for
            that question has all testcases passing).
        """
        from app.models.contest import ContestSubmission
        from app.models.question import SubmissionTestCase

        testcase_stats_subq = (
            select(
                SubmissionTestCase.submission_id.label("submission_id"),
                func.count(SubmissionTestCase.id).label("total_testcases"),
                func.coalesce(
                    func.sum(
                        case(
                            (SubmissionTestCase.status == SubmissionStatus.AC, 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("passed_testcases"),
            )
            .group_by(SubmissionTestCase.submission_id)
            .subquery()
        )

        query = (
            select(
                Submission.question_id,
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    testcase_stats_subq.c.total_testcases > 0,
                                    testcase_stats_subq.c.total_testcases
                                    == testcase_stats_subq.c.passed_testcases,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("solved_count"),
            )
            .select_from(ContestSubmission)
            .join(Submission, ContestSubmission.submission_id == Submission.id)
            .outerjoin(
                testcase_stats_subq,
                testcase_stats_subq.c.submission_id == Submission.id,
            )
            .where(
                ContestSubmission.contest_id == contest_id,
                ContestSubmission.contest_team_id == contest_team_id,
            )
            .group_by(Submission.question_id)
        )
        result = await self.db.execute(query)
        return {row.question_id: row.solved_count > 0 for row in result.all()}

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
            .options(selectinload(Submission.testcases))
            .where(
                ContestSubmission.contest_team_id == contest_team_id,
                Submission.question_id == question_id,
            )
            .order_by(Submission.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
