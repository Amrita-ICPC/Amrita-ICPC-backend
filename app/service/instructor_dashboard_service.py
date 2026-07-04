from uuid import UUID

from app.mappers.instructor_dashboard import (
    build_needs_attention,
    to_instructor_dashboard_bank,
    to_instructor_dashboard_contest,
)
from app.repositories.contest import ContestRepository
from app.repositories.dto.contest import InstructorDashboardContestRow
from app.repositories.user import UserRepository
from app.schema.instructor_dashboard import (
    InstructorDashboardContestGroups,
    InstructorDashboardResponse,
    InstructorDashboardSummary,
)
from app.service.bank_service import BankService
from app.utils.contest import compute_run_status
from app.utils.enums import BankSortBy, ContestRunStatus, UserRole


class InstructorDashboardService:
    """Aggregates contest, team-approval, evaluation, and bank state into the
    instructor dashboard view.

    This service performs no independent authorization or business logic of
    its own:
        - Contest visibility reuses ``ContestRepository``'s existing
          permission filter (the same rule the main contest listing and
          management endpoints enforce).
        - Bank visibility/sorting reuses ``BankService.get_all_banks``
          unchanged.
    This layer only classifies, aggregates, and sorts that data into the
    dashboard's shape.
    """

    def __init__(
        self,
        contest_repository: ContestRepository,
        user_repository: UserRepository,
        bank_service: BankService,
    ) -> None:
        self.contest_repository = contest_repository
        self.user_repository = user_repository
        self.bank_service = bank_service

    async def get_dashboard(
        self,
        user_id: UUID,
        contest_limit: int,
        bank_limit: int,
    ) -> InstructorDashboardResponse:
        """
        Build the instructor dashboard for the given user.

        Args:
            user_id: The requesting (instructor/manager/admin) user's ID.
            contest_limit: Max contests to return per run-status group.
            bank_limit: Max recent banks to return.

        Returns:
            InstructorDashboardResponse: Full dashboard payload.
        """
        user = await self.user_repository.get_user_or_raise(user_id)
        is_admin = user.role == UserRole.admin

        rows = await self.contest_repository.get_instructor_dashboard_contests(
            user_id=user_id, is_admin=is_admin
        )

        live, upcoming, completed = self._group_by_run_status(rows)

        pending_team_approvals = sum(row.pending_team_approvals for row in rows)
        # Scoped to ended contests: a live contest almost always has some
        # submission mid-flight through the async Judge0 pipeline, which is
        # normal and not "required work" -- only an ended contest with
        # unevaluated submissions left behind is actionable, matching the
        # PENDING_EVALUATION attention rule below.
        pending_evaluations = sum(1 for row in completed if row.pending_evaluations > 0)
        results_ready_to_publish = sum(
            1
            for row in completed
            if row.pending_evaluations == 0 and row.results_published_at is None
        )

        total_banks, recent_bank_responses = await self.bank_service.get_all_banks(
            user_id=user_id,
            skip=0,
            limit=bank_limit,
            search_term=None,
            sort_by=BankSortBy.UPDATED_NEW,
        )

        summary = InstructorDashboardSummary(
            live_contests=len(live),
            upcoming_contests=len(upcoming),
            completed_contests=len(completed),
            pending_team_approvals=pending_team_approvals,
            pending_evaluations=pending_evaluations,
            results_ready_to_publish=results_ready_to_publish,
            question_banks=total_banks,
        )

        # Needs-attention is built from every accessible contest, not just the
        # ones shown in the capped groups below, so nothing accessible is
        # silently omitted from the action list.
        needs_attention = build_needs_attention(rows)

        contests = InstructorDashboardContestGroups(
            live=[
                to_instructor_dashboard_contest(row, user_id)
                for row in sorted(live, key=lambda r: r.start_time)[:contest_limit]
            ],
            upcoming=[
                to_instructor_dashboard_contest(row, user_id)
                for row in sorted(upcoming, key=lambda r: r.start_time)[:contest_limit]
            ],
            completed=[
                to_instructor_dashboard_contest(row, user_id)
                for row in sorted(
                    completed,
                    key=lambda r: r.end_time or r.start_time,
                    reverse=True,
                )[:contest_limit]
            ],
        )

        recent_banks = [
            to_instructor_dashboard_bank(bank, user_id)
            for bank in recent_bank_responses
        ]

        return InstructorDashboardResponse(
            summary=summary,
            needs_attention=needs_attention,
            contests=contests,
            recent_banks=recent_banks,
        )

    @staticmethod
    def _group_by_run_status(
        rows: list[InstructorDashboardContestRow],
    ) -> tuple[
        list[InstructorDashboardContestRow],
        list[InstructorDashboardContestRow],
        list[InstructorDashboardContestRow],
    ]:
        """Partition contest rows into (live, upcoming, completed) via compute_run_status."""
        live: list[InstructorDashboardContestRow] = []
        upcoming: list[InstructorDashboardContestRow] = []
        completed: list[InstructorDashboardContestRow] = []

        for row in rows:
            run_status = compute_run_status(row.start_time, row.end_time)
            if run_status == ContestRunStatus.LIVE:
                live.append(row)
            elif run_status == ContestRunStatus.UPCOMING:
                upcoming.append(row)
            else:
                completed.append(row)

        return live, upcoming, completed
