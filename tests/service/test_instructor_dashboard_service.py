"""Tests for InstructorDashboardService.get_dashboard.

Contest visibility itself (creator/assigned-instructor vs. unrelated, and
admin-sees-all) is enforced by ``ContestRepository._apply_permission_filter``
-- the same rule already used by the main contest listing endpoint -- so
these tests mock the repository at that boundary and focus on what this
service actually does: derive is_admin, classify/sort/limit contests,
compute summary counts, build needs-attention items in priority order, and
map recent banks. This mirrors the existing repository/service split used
elsewhere in this codebase's test suite (e.g. tests/service/contest/).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.repositories.contest import ContestRepository
from app.repositories.dto.contest import InstructorDashboardContestRow
from app.repositories.user import UserRepository
from app.schema.bank import BankResponse
from app.service.bank_service import BankService
from app.service.instructor_dashboard_service import InstructorDashboardService
from app.utils.enums import BankSortBy, ContestMode, ContestStatus, UserRole

NOW = datetime.now(timezone.utc)


def make_row(
    *,
    name: str = "Contest",
    created_by=None,
    start_offset_hours: float = -1,
    end_offset_hours: float | None = 1,
    status: ContestStatus = ContestStatus.PUBLISHED,
    question_count: int = 3,
    registered_teams_count: int = 0,
    pending_team_approvals: int = 0,
    total_submissions: int = 0,
    pending_evaluations: int = 0,
    results_published_at: datetime | None = None,
) -> InstructorDashboardContestRow:
    """Build a raw dashboard row with a LIVE-by-default time window."""
    return InstructorDashboardContestRow(
        id=uuid4(),
        name=name,
        image=None,
        start_time=NOW + timedelta(hours=start_offset_hours),
        end_time=(
            NOW + timedelta(hours=end_offset_hours)
            if end_offset_hours is not None
            else None
        ),
        status=status,
        contest_mode=ContestMode.TEAM,
        created_by=created_by,
        results_published_at=results_published_at,
        question_count=question_count,
        registered_teams_count=registered_teams_count,
        pending_team_approvals=pending_team_approvals,
        total_submissions=total_submissions,
        pending_evaluations=pending_evaluations,
    )


def make_bank(
    *, name: str = "Bank", created_by=None, updated_at: datetime | None = None
) -> BankResponse:
    return BankResponse(
        id=uuid4(),
        name=name,
        description=None,
        created_by=created_by or uuid4(),
        created_at=NOW,
        updated_at=updated_at or NOW,
        total_questions_count=2,
    )


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def mock_contest_repository():
    return AsyncMock(spec=ContestRepository)


@pytest.fixture
def mock_user_repository():
    return AsyncMock(spec=UserRepository)


@pytest.fixture
def mock_bank_service():
    service = AsyncMock(spec=BankService)
    service.get_all_banks.return_value = (0, [])
    return service


@pytest.fixture
def service(mock_contest_repository, mock_user_repository, mock_bank_service):
    return InstructorDashboardService(
        contest_repository=mock_contest_repository,
        user_repository=mock_user_repository,
        bank_service=mock_bank_service,
    )


def _set_user_role(mock_user_repository, role: UserRole, user_id):
    user = MagicMock()
    user.id = user_id
    user.role = role
    mock_user_repository.get_user_or_raise.return_value = user


class TestAuthorizationDelegation:
    """The service must derive is_admin from the user's role and pass it
    through unchanged to the shared, pre-existing permission filter -- it
    must never broaden or narrow visibility itself."""

    @pytest.mark.asyncio
    async def test_instructor_role_queries_as_non_admin(
        self,
        service,
        mock_contest_repository,
        mock_user_repository,
        mock_bank_service,
        user_id,
    ):
        _set_user_role(mock_user_repository, UserRole.instructor, user_id)
        mock_contest_repository.get_instructor_dashboard_contests.return_value = []

        await service.get_dashboard(user_id, contest_limit=5, bank_limit=4)

        mock_contest_repository.get_instructor_dashboard_contests.assert_awaited_once_with(
            user_id=user_id, is_admin=False
        )

    @pytest.mark.asyncio
    async def test_admin_role_queries_as_admin(
        self, service, mock_contest_repository, mock_user_repository, user_id
    ):
        _set_user_role(mock_user_repository, UserRole.admin, user_id)
        mock_contest_repository.get_instructor_dashboard_contests.return_value = []

        await service.get_dashboard(user_id, contest_limit=5, bank_limit=4)

        mock_contest_repository.get_instructor_dashboard_contests.assert_awaited_once_with(
            user_id=user_id, is_admin=True
        )

    @pytest.mark.asyncio
    async def test_manager_role_is_not_broadened_by_existing_rules(
        self, service, mock_contest_repository, mock_user_repository, user_id
    ):
        """Documents an explicit assumption: the existing permission filter
        (_apply_permission_filter / ContestPermission.is_admin) only special-
        cases UserRole.admin. A manager who never created or was assigned a
        contest therefore sees an empty dashboard, exactly like an
        instructor would -- this service does not invent a broader rule."""
        _set_user_role(mock_user_repository, UserRole.manager, user_id)
        mock_contest_repository.get_instructor_dashboard_contests.return_value = []

        await service.get_dashboard(user_id, contest_limit=5, bank_limit=4)

        mock_contest_repository.get_instructor_dashboard_contests.assert_awaited_once_with(
            user_id=user_id, is_admin=False
        )


class TestContestOwnershipFlag:
    @pytest.mark.asyncio
    async def test_created_contest_is_flagged_as_own(
        self, service, mock_contest_repository, mock_user_repository, user_id
    ):
        _set_user_role(mock_user_repository, UserRole.instructor, user_id)
        row = make_row(name="My Contest", created_by=user_id)
        mock_contest_repository.get_instructor_dashboard_contests.return_value = [row]

        result = await service.get_dashboard(user_id, contest_limit=5, bank_limit=4)

        assert result.contests.live[0].created_by_current_user is True

    @pytest.mark.asyncio
    async def test_assigned_contest_not_flagged_as_own(
        self, service, mock_contest_repository, mock_user_repository, user_id
    ):
        """Repository returns this row because the user is an assigned
        instructor (per _apply_permission_filter), but a different user
        created it -- created_by_current_user must reflect that."""
        other_creator = uuid4()
        _set_user_role(mock_user_repository, UserRole.instructor, user_id)
        row = make_row(name="Assigned Contest", created_by=other_creator)
        mock_contest_repository.get_instructor_dashboard_contests.return_value = [row]

        result = await service.get_dashboard(user_id, contest_limit=5, bank_limit=4)

        assert result.contests.live[0].created_by_current_user is False


class TestContestGrouping:
    @pytest.mark.asyncio
    async def test_live_upcoming_completed_grouping_and_sort_order(
        self, service, mock_contest_repository, mock_user_repository, user_id
    ):
        _set_user_role(mock_user_repository, UserRole.instructor, user_id)

        live_early = make_row(
            name="Live Early", start_offset_hours=-2, end_offset_hours=1
        )
        live_late = make_row(
            name="Live Late", start_offset_hours=-1, end_offset_hours=1
        )
        upcoming_soon = make_row(
            name="Upcoming Soon", start_offset_hours=1, end_offset_hours=2
        )
        upcoming_later = make_row(
            name="Upcoming Later", start_offset_hours=5, end_offset_hours=6
        )
        completed_recent = make_row(
            name="Completed Recent", start_offset_hours=-10, end_offset_hours=-1
        )
        completed_older = make_row(
            name="Completed Older", start_offset_hours=-20, end_offset_hours=-5
        )
        rows = [
            live_late,
            live_early,
            upcoming_later,
            upcoming_soon,
            completed_older,
            completed_recent,
        ]
        mock_contest_repository.get_instructor_dashboard_contests.return_value = rows

        result = await service.get_dashboard(user_id, contest_limit=5, bank_limit=4)

        assert [c.name for c in result.contests.live] == ["Live Early", "Live Late"]
        assert [c.name for c in result.contests.upcoming] == [
            "Upcoming Soon",
            "Upcoming Later",
        ]
        assert [c.name for c in result.contests.completed] == [
            "Completed Recent",
            "Completed Older",
        ]
        assert result.summary.live_contests == 2
        assert result.summary.upcoming_contests == 2
        assert result.summary.completed_contests == 2

    @pytest.mark.asyncio
    async def test_contest_limit_truncates_each_group_independently(
        self, service, mock_contest_repository, mock_user_repository, user_id
    ):
        _set_user_role(mock_user_repository, UserRole.instructor, user_id)
        live_rows = [
            make_row(name=f"Live {i}", start_offset_hours=-i, end_offset_hours=10)
            for i in range(5)
        ]
        mock_contest_repository.get_instructor_dashboard_contests.return_value = (
            live_rows
        )

        result = await service.get_dashboard(user_id, contest_limit=2, bank_limit=4)

        # Group is capped to contest_limit, but the summary count reflects
        # every accessible LIVE contest, not just the ones displayed.
        assert len(result.contests.live) == 2
        assert result.summary.live_contests == 5


class TestPendingApprovalsAndEvaluations:
    @pytest.mark.asyncio
    async def test_pending_team_approvals_summed_across_contests(
        self, service, mock_contest_repository, mock_user_repository, user_id
    ):
        _set_user_role(mock_user_repository, UserRole.instructor, user_id)
        rows = [
            make_row(name="A", pending_team_approvals=2),
            make_row(name="B", pending_team_approvals=3),
        ]
        mock_contest_repository.get_instructor_dashboard_contests.return_value = rows

        result = await service.get_dashboard(user_id, contest_limit=5, bank_limit=4)

        assert result.summary.pending_team_approvals == 5

    @pytest.mark.asyncio
    async def test_pending_evaluations_only_counts_ended_contests(
        self, service, mock_contest_repository, mock_user_repository, user_id
    ):
        """A live contest with in-flight (unevaluated) submissions is normal
        async-pipeline behavior, not actionable work -- only an ended
        contest with leftover unevaluated submissions counts."""
        _set_user_role(mock_user_repository, UserRole.instructor, user_id)
        live_with_pending = make_row(
            name="Live",
            start_offset_hours=-1,
            end_offset_hours=1,
            pending_evaluations=4,
        )
        ended_with_pending = make_row(
            name="Ended",
            start_offset_hours=-10,
            end_offset_hours=-1,
            pending_evaluations=2,
        )
        rows = [live_with_pending, ended_with_pending]
        mock_contest_repository.get_instructor_dashboard_contests.return_value = rows

        result = await service.get_dashboard(user_id, contest_limit=5, bank_limit=4)

        assert result.summary.pending_evaluations == 1


class TestResultsReadyToPublish:
    @pytest.mark.asyncio
    async def test_results_ready_detected_for_fully_evaluated_ended_contest(
        self, service, mock_contest_repository, mock_user_repository, user_id
    ):
        _set_user_role(mock_user_repository, UserRole.instructor, user_id)
        row = make_row(
            name="Ready Contest",
            start_offset_hours=-10,
            end_offset_hours=-1,
            pending_evaluations=0,
            results_published_at=None,
        )
        mock_contest_repository.get_instructor_dashboard_contests.return_value = [row]

        result = await service.get_dashboard(user_id, contest_limit=5, bank_limit=4)

        assert result.summary.results_ready_to_publish == 1
        assert any(
            item.type == "RESULTS_READY" and item.contest_name == "Ready Contest"
            for item in result.needs_attention
        )

    @pytest.mark.asyncio
    async def test_already_published_contest_is_not_results_ready(
        self, service, mock_contest_repository, mock_user_repository, user_id
    ):
        _set_user_role(mock_user_repository, UserRole.instructor, user_id)
        row = make_row(
            name="Published Contest",
            start_offset_hours=-10,
            end_offset_hours=-1,
            pending_evaluations=0,
            results_published_at=NOW,
        )
        mock_contest_repository.get_instructor_dashboard_contests.return_value = [row]

        result = await service.get_dashboard(user_id, contest_limit=5, bank_limit=4)

        assert result.summary.results_ready_to_publish == 0
        assert not any(item.type == "RESULTS_READY" for item in result.needs_attention)


class TestNeedsAttentionOrdering:
    @pytest.mark.asyncio
    async def test_ordering_prioritizes_live_contests_then_type(
        self, service, mock_contest_repository, mock_user_repository, user_id
    ):
        # Non-live results-ready item: lowest type priority among non-live.
        ended_results_ready = make_row(
            name="Ended Results Ready",
            start_offset_hours=-10,
            end_offset_hours=-1,
            pending_evaluations=0,
            results_published_at=None,
        )
        # Non-live pending-evaluation item: higher type priority than results-ready.
        ended_pending_eval = make_row(
            name="Ended Pending Eval",
            start_offset_hours=-10,
            end_offset_hours=-1,
            pending_evaluations=1,
        )
        # Live contest with a team-approval issue: must sort before all non-live items.
        live_team_approval = make_row(
            name="Live Approval",
            start_offset_hours=-1,
            end_offset_hours=1,
            pending_team_approvals=1,
        )
        _set_user_role(mock_user_repository, UserRole.instructor, user_id)
        rows = [ended_results_ready, ended_pending_eval, live_team_approval]
        mock_contest_repository.get_instructor_dashboard_contests.return_value = rows

        result = await service.get_dashboard(user_id, contest_limit=5, bank_limit=4)

        names_in_order = [item.contest_name for item in result.needs_attention]
        assert names_in_order == [
            "Live Approval",
            "Ended Pending Eval",
            "Ended Results Ready",
        ]

    @pytest.mark.asyncio
    async def test_missing_questions_only_for_published_upcoming_with_zero_questions(
        self, service, mock_contest_repository, mock_user_repository, user_id
    ):
        _set_user_role(mock_user_repository, UserRole.instructor, user_id)
        flagged = make_row(
            name="Upcoming No Questions",
            start_offset_hours=1,
            end_offset_hours=2,
            status=ContestStatus.PUBLISHED,
            question_count=0,
        )
        not_flagged_has_questions = make_row(
            name="Upcoming Has Questions",
            start_offset_hours=1,
            end_offset_hours=2,
            status=ContestStatus.PUBLISHED,
            question_count=5,
        )
        not_flagged_draft = make_row(
            name="Draft No Questions",
            start_offset_hours=1,
            end_offset_hours=2,
            status=ContestStatus.DRAFT,
            question_count=0,
        )
        rows = [flagged, not_flagged_has_questions, not_flagged_draft]
        mock_contest_repository.get_instructor_dashboard_contests.return_value = rows

        result = await service.get_dashboard(user_id, contest_limit=5, bank_limit=4)

        missing_question_items = [
            item for item in result.needs_attention if item.type == "MISSING_QUESTIONS"
        ]
        assert len(missing_question_items) == 1
        assert missing_question_items[0].contest_name == "Upcoming No Questions"

    @pytest.mark.asyncio
    async def test_no_duplicate_item_types_for_same_contest(
        self, service, mock_contest_repository, mock_user_repository, user_id
    ):
        _set_user_role(mock_user_repository, UserRole.instructor, user_id)
        row = make_row(
            name="Busy Contest",
            start_offset_hours=-1,
            end_offset_hours=1,
            pending_team_approvals=3,
        )
        mock_contest_repository.get_instructor_dashboard_contests.return_value = [row]

        result = await service.get_dashboard(user_id, contest_limit=5, bank_limit=4)

        types_for_contest = [
            item.type
            for item in result.needs_attention
            if item.contest_name == "Busy Contest"
        ]
        assert len(types_for_contest) == len(set(types_for_contest))


class TestRecentBanks:
    @pytest.mark.asyncio
    async def test_recent_banks_mapped_with_ownership_flag_and_limit_passed_through(
        self,
        service,
        mock_contest_repository,
        mock_user_repository,
        mock_bank_service,
        user_id,
    ):
        _set_user_role(mock_user_repository, UserRole.instructor, user_id)
        mock_contest_repository.get_instructor_dashboard_contests.return_value = []
        owned_bank = make_bank(name="Owned", created_by=user_id)
        shared_bank = make_bank(name="Shared", created_by=uuid4())
        mock_bank_service.get_all_banks.return_value = (7, [owned_bank, shared_bank])

        result = await service.get_dashboard(user_id, contest_limit=5, bank_limit=2)

        mock_bank_service.get_all_banks.assert_awaited_once_with(
            user_id=user_id,
            skip=0,
            limit=2,
            search_term=None,
            sort_by=BankSortBy.UPDATED_NEW,
        )
        assert result.summary.question_banks == 7
        assert [b.name for b in result.recent_banks] == ["Owned", "Shared"]
        assert result.recent_banks[0].is_owner is True
        assert result.recent_banks[1].is_owner is False


class TestEmptyDashboard:
    @pytest.mark.asyncio
    async def test_empty_dashboard_when_nothing_accessible(
        self,
        service,
        mock_contest_repository,
        mock_user_repository,
        mock_bank_service,
        user_id,
    ):
        _set_user_role(mock_user_repository, UserRole.instructor, user_id)
        mock_contest_repository.get_instructor_dashboard_contests.return_value = []
        mock_bank_service.get_all_banks.return_value = (0, [])

        result = await service.get_dashboard(user_id, contest_limit=5, bank_limit=4)

        assert result.summary.live_contests == 0
        assert result.summary.upcoming_contests == 0
        assert result.summary.completed_contests == 0
        assert result.summary.pending_team_approvals == 0
        assert result.summary.pending_evaluations == 0
        assert result.summary.results_ready_to_publish == 0
        assert result.summary.question_banks == 0
        assert result.needs_attention == []
        assert result.contests.live == []
        assert result.contests.upcoming == []
        assert result.contests.completed == []
        assert result.recent_banks == []
