import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contest import (
    ContestQuestion,
    ContestSubmission,
    ContestTeam,
    ContestTeamMember,
)
from app.models.language import Language
from app.models.question import Question, Submission
from app.models.user import User
from app.repositories.dto.submission import (
    ContestAnalyticsRaw,
    ContestDashboardRawData,
    ProblemHealthRaw,
    RecentSubmissionRaw,
    TeamPerformanceRaw,
)
from app.utils.enums import SubmissionStatus


class ContestSubmissionRepository:
    """Repository for querying contest submission and aggregate dashboard data."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard_analytics_raw(
        self, contest_id: uuid.UUID
    ) -> ContestDashboardRawData:
        """
        Query all raw aggregate statistics and models for the contest dashboard.

        Executes efficient, database-level aggregate SQL queries (avoiding N+1 loops)
        and transfers them to the service layer as simple repository DTOs.

        Args:
            contest_id: Unique identifier of the contest.

        Returns:
            ContestDashboardRawData: Contains raw queries results for analytics,
            problem health, team performance, and recent submissions.
        """
        from app.models.question import SubmissionTestCase

        # Helper subquery to compute the status of each submission dynamically
        sub_status_subq = (
            select(
                SubmissionTestCase.submission_id,
                case(
                    (
                        func.sum(
                            case(
                                (
                                    SubmissionTestCase.status
                                    == SubmissionStatus.SYSTEM_ERROR,
                                    1,
                                ),
                                else_=0,
                            )
                        )
                        > 0,
                        SubmissionStatus.SYSTEM_ERROR,
                    ),
                    (
                        func.sum(
                            case(
                                (SubmissionTestCase.status == SubmissionStatus.CE, 1),
                                else_=0,
                            )
                        )
                        > 0,
                        SubmissionStatus.CE,
                    ),
                    (
                        func.sum(
                            case(
                                (SubmissionTestCase.status == SubmissionStatus.MLE, 1),
                                else_=0,
                            )
                        )
                        > 0,
                        SubmissionStatus.MLE,
                    ),
                    (
                        func.sum(
                            case(
                                (SubmissionTestCase.status == SubmissionStatus.TLE, 1),
                                else_=0,
                            )
                        )
                        > 0,
                        SubmissionStatus.TLE,
                    ),
                    (
                        func.sum(
                            case(
                                (SubmissionTestCase.status == SubmissionStatus.RE, 1),
                                else_=0,
                            )
                        )
                        > 0,
                        SubmissionStatus.RE,
                    ),
                    (
                        func.sum(
                            case(
                                (SubmissionTestCase.status == SubmissionStatus.WA, 1),
                                else_=0,
                            )
                        )
                        > 0,
                        SubmissionStatus.WA,
                    ),
                    else_=SubmissionStatus.AC,
                ).label("computed_status"),
            )
            .group_by(SubmissionTestCase.submission_id)
            .subquery()
        )

        # 1. Query Contest Analytics (Verdict breakdown counts)
        analytics_query = (
            select(
                func.count(Submission.id).label("total_submissions"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                sub_status_subq.c.computed_status
                                == SubmissionStatus.AC,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("accepted"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                sub_status_subq.c.computed_status
                                == SubmissionStatus.WA,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("wrong_answer"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                sub_status_subq.c.computed_status
                                == SubmissionStatus.TLE,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("time_limit_exceeded"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                sub_status_subq.c.computed_status
                                == SubmissionStatus.RE,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("runtime_error"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                sub_status_subq.c.computed_status
                                == SubmissionStatus.CE,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("compilation_error"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                sub_status_subq.c.computed_status
                                == SubmissionStatus.MLE,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("memory_limit_exceeded"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                sub_status_subq.c.computed_status
                                == SubmissionStatus.SYSTEM_ERROR,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("system_error"),
            )
            .select_from(ContestSubmission)
            .join(Submission, ContestSubmission.submission_id == Submission.id)
            .outerjoin(
                sub_status_subq, sub_status_subq.c.submission_id == Submission.id
            )
            .where(ContestSubmission.contest_id == contest_id)
        )
        analytics_result = await self.db.execute(analytics_query)
        analytics_row = analytics_result.first()

        if analytics_row:
            analytics_dto = ContestAnalyticsRaw(
                total_submissions=analytics_row.total_submissions,
                accepted=analytics_row.accepted,
                wrong_answer=analytics_row.wrong_answer,
                time_limit_exceeded=analytics_row.time_limit_exceeded,
                runtime_error=analytics_row.runtime_error,
                compilation_error=analytics_row.compilation_error,
                memory_limit_exceeded=analytics_row.memory_limit_exceeded,
                system_error=analytics_row.system_error,
            )
        else:
            analytics_dto = ContestAnalyticsRaw(
                total_submissions=0,
                accepted=0,
                wrong_answer=0,
                time_limit_exceeded=0,
                runtime_error=0,
                compilation_error=0,
                memory_limit_exceeded=0,
                system_error=0,
            )

        # 2. Query Problem Health
        subq_submissions = (
            select(
                Submission.question_id,
                func.count(Submission.id).label("attempts"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                sub_status_subq.c.computed_status
                                == SubmissionStatus.AC,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("accepted"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                sub_status_subq.c.computed_status
                                == SubmissionStatus.SYSTEM_ERROR,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("system_errors"),
            )
            .select_from(ContestSubmission)
            .join(Submission, ContestSubmission.submission_id == Submission.id)
            .outerjoin(
                sub_status_subq, sub_status_subq.c.submission_id == Submission.id
            )
            .where(ContestSubmission.contest_id == contest_id)
            .group_by(Submission.question_id)
            .subquery()
        )

        health_query = (
            select(
                Question.id,
                Question.title,
                Question.difficulty,
                func.coalesce(subq_submissions.c.attempts, 0).label("attempts"),
                func.coalesce(subq_submissions.c.accepted, 0).label("accepted"),
                func.coalesce(subq_submissions.c.system_errors, 0).label(
                    "system_errors"
                ),
            )
            .select_from(ContestQuestion)
            .join(Question, ContestQuestion.question_id == Question.id)
            .outerjoin(subq_submissions, subq_submissions.c.question_id == Question.id)
            .where(ContestQuestion.contest_id == contest_id)
            .order_by(ContestQuestion.order)
        )
        health_result = await self.db.execute(health_query)
        health_rows = health_result.all()

        problem_health_dtos = [
            ProblemHealthRaw(
                id=r.id,
                title=r.title,
                difficulty=r.difficulty,
                attempts=r.attempts,
                accepted=r.accepted,
                system_errors=r.system_errors,
            )
            for r in health_rows
        ]

        # 3. Query Team Performance
        team_subq = (
            select(
                ContestSubmission.contest_team_id,
                func.count(Submission.id).label("total_attempts"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                sub_status_subq.c.computed_status
                                == SubmissionStatus.AC,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("accepted_attempts"),
                func.count(
                    func.distinct(
                        case(
                            (
                                sub_status_subq.c.computed_status
                                == SubmissionStatus.AC,
                                Submission.question_id,
                            ),
                            else_=None,
                        )
                    )
                ).label("solved"),
                func.count(func.distinct(Submission.question_id)).label("attempted"),
                func.max(Submission.created_at).label("last_activity_at"),
            )
            .select_from(ContestSubmission)
            .join(Submission, ContestSubmission.submission_id == Submission.id)
            .outerjoin(
                sub_status_subq, sub_status_subq.c.submission_id == Submission.id
            )
            .where(ContestSubmission.contest_id == contest_id)
            .group_by(ContestSubmission.contest_team_id)
            .subquery()
        )

        team_query = (
            select(
                ContestTeam.id,
                ContestTeam.name,
                func.coalesce(team_subq.c.solved, 0).label("solved"),
                func.coalesce(team_subq.c.attempted, 0).label("attempted"),
                func.coalesce(team_subq.c.total_attempts, 0).label("total_attempts"),
                func.coalesce(team_subq.c.accepted_attempts, 0).label(
                    "accepted_attempts"
                ),
                team_subq.c.last_activity_at.label("last_activity_at"),
            )
            .select_from(ContestTeam)
            .outerjoin(team_subq, team_subq.c.contest_team_id == ContestTeam.id)
            .where(ContestTeam.contest_id == contest_id)
            .order_by(ContestTeam.name)
        )
        team_result = await self.db.execute(team_query)
        team_rows = team_result.all()

        team_performance_dtos = [
            TeamPerformanceRaw(
                id=r.id,
                name=r.name,
                solved=r.solved,
                attempted=r.attempted,
                total_attempts=r.total_attempts,
                accepted_attempts=r.accepted_attempts,
                last_activity_at=r.last_activity_at,
            )
            for r in team_rows
        ]

        # 4. Query Recent Submissions
        recent_query = (
            select(
                Submission.id,
                User.id.label("user_id"),
                User.name.label("user_name"),
                ContestTeam.id.label("team_id"),
                ContestTeam.name.label("team_name"),
                Question.id.label("question_id"),
                Question.title.label("question_title"),
                Language.name.label("language_name"),
                sub_status_subq.c.computed_status.label("status"),
                Submission.created_at,
            )
            .select_from(ContestSubmission)
            .join(Submission, ContestSubmission.submission_id == Submission.id)
            .outerjoin(
                sub_status_subq, sub_status_subq.c.submission_id == Submission.id
            )
            .join(Language, Submission.language_id == Language.id)
            .join(Question, Submission.question_id == Question.id)
            .join(
                ContestTeamMember,
                ContestSubmission.contest_team_member_id == ContestTeamMember.id,
            )
            .join(User, ContestTeamMember.user_id == User.id)
            .outerjoin(ContestTeam, ContestSubmission.contest_team_id == ContestTeam.id)
            .where(ContestSubmission.contest_id == contest_id)
            .order_by(Submission.created_at.desc())
            .limit(8)
        )
        recent_result = await self.db.execute(recent_query)
        recent_rows = recent_result.all()

        recent_submission_dtos = [
            RecentSubmissionRaw(
                id=r.id,
                user_id=r.user_id,
                user_name=r.user_name,
                team_id=r.team_id,
                team_name=r.team_name,
                question_id=r.question_id,
                question_title=r.question_title,
                language_name=r.language_name,
                status=r.status,
                created_at=r.created_at,
            )
            for r in recent_rows
        ]

        return ContestDashboardRawData(
            analytics=analytics_dto,
            problem_health=problem_health_dtos,
            team_performance=team_performance_dtos,
            recent_submissions=recent_submission_dtos,
        )
