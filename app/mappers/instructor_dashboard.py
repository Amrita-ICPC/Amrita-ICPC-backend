from uuid import UUID

from app.repositories.dto.contest import InstructorDashboardContestRow
from app.schema.bank import BankResponse
from app.schema.instructor_dashboard import (
    InstructorDashboardAttentionItem,
    InstructorDashboardBank,
    InstructorDashboardContest,
)
from app.utils.contest import compute_run_status
from app.utils.enums import ContestRunStatus, ContestStatus
from app.utils.image import image_object_key_to_url

# Secondary sort key for needs-attention items: within the same live/non-live
# partition, order by issue type. Lower sorts first.
_ATTENTION_TYPE_PRIORITY = {
    "TEAM_APPROVAL": 0,
    "PENDING_EVALUATION": 1,
    "RESULTS_READY": 2,
    "MISSING_QUESTIONS": 3,
}


def to_instructor_dashboard_contest(
    row: InstructorDashboardContestRow, user_id: UUID
) -> InstructorDashboardContest:
    """Map a raw dashboard contest row to its lightweight response schema."""
    return InstructorDashboardContest(
        id=row.id,
        name=row.name,
        image=image_object_key_to_url(row.image),
        start_time=row.start_time,
        end_time=row.end_time,
        run_status=compute_run_status(row.start_time, row.end_time),
        status=row.status,
        contest_mode=row.contest_mode,
        question_count=row.question_count,
        registered_teams_count=row.registered_teams_count,
        pending_team_approvals=row.pending_team_approvals,
        total_submissions=row.total_submissions,
        results_published_at=row.results_published_at,
        created_by_current_user=row.created_by == user_id,
    )


def to_instructor_dashboard_bank(
    bank: BankResponse, user_id: UUID
) -> InstructorDashboardBank:
    """Map a BankResponse (from the existing bank listing) to the dashboard's bank schema."""
    return InstructorDashboardBank(
        id=bank.id,
        name=bank.name,
        description=bank.description,
        question_count=bank.total_questions_count,
        updated_at=bank.updated_at,
        is_owner=bank.created_by == user_id,
    )


def build_needs_attention(
    rows: list[InstructorDashboardContestRow],
) -> list[InstructorDashboardAttentionItem]:
    """
    Build actionable attention items from the accessible contests' breakdowns.

    Produces at most one item per (contest, type) by construction (each rule
    below appends at most once per row), then orders the result so that:
    1. Issues on currently-LIVE contests come first, regardless of type.
    2. Within that, items are ordered by type: team approvals, pending
       evaluations, results ready to publish, then missing questions.

    Args:
        rows: Every contest accessible to the requesting user (not just the
            ones shown in the capped contest groups), so nothing accessible
            is silently left out of the attention list.

    Returns:
        Ordered list of attention items.
    """
    items: list[InstructorDashboardAttentionItem] = []
    run_status_by_id: dict[UUID, ContestRunStatus] = {}

    for row in rows:
        run_status = compute_run_status(row.start_time, row.end_time)
        run_status_by_id[row.id] = run_status

        if row.pending_team_approvals > 0:
            items.append(
                InstructorDashboardAttentionItem(
                    type="TEAM_APPROVAL",
                    contest_id=row.id,
                    contest_name=row.name,
                    count=row.pending_team_approvals,
                    message=(
                        f"{row.pending_team_approvals} team(s) awaiting approval "
                        f"in '{row.name}'"
                    ),
                )
            )

        if (
            row.status == ContestStatus.PUBLISHED
            and run_status == ContestRunStatus.UPCOMING
            and row.question_count == 0
        ):
            items.append(
                InstructorDashboardAttentionItem(
                    type="MISSING_QUESTIONS",
                    contest_id=row.id,
                    contest_name=row.name,
                    count=None,
                    message=f"'{row.name}' has no questions added yet",
                )
            )

        if run_status == ContestRunStatus.ENDED:
            if row.pending_evaluations > 0:
                items.append(
                    InstructorDashboardAttentionItem(
                        type="PENDING_EVALUATION",
                        contest_id=row.id,
                        contest_name=row.name,
                        count=row.pending_evaluations,
                        message=(
                            f"{row.pending_evaluations} submission(s) pending "
                            f"evaluation in '{row.name}'"
                        ),
                    )
                )
            elif row.results_published_at is None:
                items.append(
                    InstructorDashboardAttentionItem(
                        type="RESULTS_READY",
                        contest_id=row.id,
                        contest_name=row.name,
                        count=None,
                        message=f"Results are ready to publish for '{row.name}'",
                    )
                )

    def sort_key(item: InstructorDashboardAttentionItem) -> tuple:
        is_live = run_status_by_id.get(item.contest_id) == ContestRunStatus.LIVE
        return (
            0 if is_live else 1,
            _ATTENTION_TYPE_PRIORITY[item.type],
            item.contest_name,
        )

    items.sort(key=sort_key)
    return items
