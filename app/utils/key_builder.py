from uuid import UUID


def build_workspace_key(
    contest_id: UUID,
    question_id: UUID,
    contest_team_member_id: UUID,
) -> str:
    return (
        f"contest_workspace:{contest_id}:member:{contest_team_member_id}:{question_id}"
    )


def get_contest_channel_key(contest_id: UUID) -> str:
    return f"contest:{contest_id}:events"
