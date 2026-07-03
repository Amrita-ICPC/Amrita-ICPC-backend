import uuid

from app.core.guards.contest import ContestOperationGuard
from app.exceptions.contest import ContestNotFoundError
from app.repositories.contest import ContestRepository
from app.repositories.submission import ContestSubmissionRepository
from app.repositories.team import TeamRepository
from app.schema.submission import (
    ContestAnalyticsSchema,
    ContestDashboardResponse,
    ContestResultsResponse,
    NeedsAttentionSchema,
    ProblematicQuestionSchema,
    ProblemHealthSchema,
    RecentSubmissionSchema,
    SubmissionQuestionSchema,
    SubmissionTeamSchema,
    SubmissionUserSchema,
    TeamPerformanceSchema,
)
from app.utils.enums import ContestStatus


class ContestDashboardService:
    """Service to orchestrate permissions, map repository DTOs, and format the contest dashboard."""

    def __init__(
        self,
        contest_repository: ContestRepository,
        submission_repository: ContestSubmissionRepository,
        guard: ContestOperationGuard,
        team_repository: TeamRepository,
    ):
        self.contest_repository = contest_repository
        self.submission_repository = submission_repository
        self.guard = guard
        self.team_repository = team_repository

    async def get_dashboard_analytics(
        self, contest_id: uuid.UUID, user_id: uuid.UUID
    ) -> ContestDashboardResponse:
        """
        Verify permission and retrieve full dashboard analytics for a contest.

        All business calculations and schema mappings are done in this service layer.

        Args:
            contest_id: The UUID of the contest.
            user_id: The UUID of the requesting user.

        Returns:
            ContestDashboardResponse containing all dashboard metrics.

        Raises:
            ContestNotFoundError: If the contest is not found or is soft-deleted.
            PermissionDeniedError: If the user lacks manage permissions for this contest.
        """
        # 1. Retrieve contest and check existence/soft-deletion
        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        if contest.status == ContestStatus.DELETED:
            raise ContestNotFoundError(str(contest_id))

        # 2. Enforce manage contest permissions (Creator, assigned instructors, or admins)
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        # 3. Retrieve raw aggregated query results from the repository layer
        raw_data = await self.submission_repository.get_dashboard_analytics_raw(
            contest_id
        )

        # 4. Map Contest Analytics (Verdict breakdown counts)
        contest_analytics = ContestAnalyticsSchema(
            total_submissions=raw_data.analytics.total_submissions,
            accepted=raw_data.analytics.accepted,
            wrong_answer=raw_data.analytics.wrong_answer,
            time_limit_exceeded=raw_data.analytics.time_limit_exceeded,
            runtime_error=raw_data.analytics.runtime_error,
            compilation_error=raw_data.analytics.compilation_error,
            memory_limit_exceeded=raw_data.analytics.memory_limit_exceeded,
            system_error=raw_data.analytics.system_error,
        )

        # 5. Map Problem Health & Compute Acceptance Rates
        problem_health = []
        for p in raw_data.problem_health:
            acc_rate = (p.accepted / p.attempts * 100.0) if p.attempts > 0 else 0.0
            problem_health.append(
                ProblemHealthSchema(
                    id=p.id,
                    title=p.title,
                    difficulty=p.difficulty,
                    attempts=p.attempts,
                    accepted=p.accepted,
                    acceptance_rate=acc_rate,
                    system_errors=p.system_errors,
                )
            )

        # 6. Map Needs Attention (identify problematic questions and total system errors)
        total_system_errors = sum(q.system_errors for q in problem_health)
        problematic_questions = []
        for q in problem_health:
            # A question needs attention if it has attempts and acceptance rate is < 40%, or it has system errors
            if q.attempts > 0 and (q.acceptance_rate < 40.0 or q.system_errors > 0):
                problematic_questions.append(
                    ProblematicQuestionSchema(
                        id=q.id,
                        title=q.title,
                        difficulty=q.difficulty,
                        attempts=q.attempts,
                        acceptance_rate=q.acceptance_rate,
                    )
                )

        needs_attention = NeedsAttentionSchema(
            system_errors=total_system_errors,
            problematic_questions=problematic_questions,
        )

        # 7. Map Team Performance & Compute Metrics
        team_performance = []
        for t in raw_data.team_performance:
            failed_attempts = t.total_attempts - t.accepted_attempts
            acc_rate = (
                (t.accepted_attempts / t.total_attempts * 100.0)
                if t.total_attempts > 0
                else 0.0
            )

            team_performance.append(
                TeamPerformanceSchema(
                    id=t.id,
                    name=t.name,
                    solved=t.solved,
                    attempted=t.attempted,
                    failed=failed_attempts,
                    acceptance_rate=acc_rate,
                    last_activity_at=t.last_activity_at,
                )
            )

        # 8. Map Recent Submissions
        recent_submissions = []
        for r in raw_data.recent_submissions:
            team_schema = None
            if r.team_id and r.team_name is not None:
                team_schema = SubmissionTeamSchema(id=r.team_id, name=r.team_name)

            recent_submissions.append(
                RecentSubmissionSchema(
                    id=r.id,
                    submitted_by=SubmissionUserSchema(id=r.user_id, name=r.user_name),
                    team=team_schema,
                    question=SubmissionQuestionSchema(
                        id=r.question_id, title=r.question_title
                    ),
                    language=r.language_name,
                    status=r.status,
                    created_at=r.created_at,
                )
            )

        return ContestDashboardResponse(
            contest_analytics=contest_analytics,
            needs_attention=needs_attention,
            team_performance=team_performance,
            problem_health=problem_health,
            recent_submissions=recent_submissions,
        )

    async def get_contest_results(
        self, contest_id: uuid.UUID, user_id: uuid.UUID
    ) -> ContestResultsResponse:
        """
        Verify permission and retrieve the results-page summary for a contest.

        Reuses the same submission-statistics query as the dashboard (rather than
        issuing a separate count query) and adds the flagged-progress count.

        Args:
            contest_id: The UUID of the contest.
            user_id: The UUID of the requesting user.

        Returns:
            ContestResultsResponse containing total responses, submission
            statistics, and the flagged response count.

        Raises:
            ContestNotFoundError: If the contest is not found or is soft-deleted.
            PermissionDeniedError: If the user lacks manage permissions for this contest.
        """
        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        if contest.status == ContestStatus.DELETED:
            raise ContestNotFoundError(str(contest_id))

        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        analytics_raw = await self.submission_repository.get_contest_analytics_raw(
            contest_id
        )
        flagged_count = await self.team_repository.count_flagged_progress_in_contest(
            contest_id
        )

        submission_statistics = ContestAnalyticsSchema(
            total_submissions=analytics_raw.total_submissions,
            accepted=analytics_raw.accepted,
            wrong_answer=analytics_raw.wrong_answer,
            time_limit_exceeded=analytics_raw.time_limit_exceeded,
            runtime_error=analytics_raw.runtime_error,
            compilation_error=analytics_raw.compilation_error,
            memory_limit_exceeded=analytics_raw.memory_limit_exceeded,
            system_error=analytics_raw.system_error,
        )

        return ContestResultsResponse(
            total_responses=analytics_raw.total_submissions,
            submission_statistics=submission_statistics,
            flagged_responses=flagged_count,
        )
