from uuid import UUID


def build_workspace_key(
    contest_id: UUID,
    question_id: UUID,
    contest_team_member_id: UUID,
) -> str:
    return (
        f"contest_workspace:{contest_id}:member:{contest_team_member_id}:{question_id}"
    )


def build_question_view_key(
    contest_id: UUID,
    contest_team_member_id: UUID,
    question_id: UUID,
) -> str:
    return f"contests:{contest_id}:members:{contest_team_member_id}:questions:{question_id}:status"


def get_contest_channel_key(
    contest_id: UUID,
    team_id: UUID | None = None,
    contest_team_member_id: UUID | None = None,
) -> str:
    if team_id and contest_team_member_id:
        return f"contest:{contest_id}:team:{team_id}:members:{contest_team_member_id}"
    return f"contest:{contest_id}:events"


def build_submission_slot_lock_key(
    contest_id: UUID,
    contest_team_member_id: UUID,
    question_id: UUID,
) -> str:
    return (
        f"contest:{contest_id}:member:{contest_team_member_id}"
        f":question:{question_id}:submission_slot"
    )
