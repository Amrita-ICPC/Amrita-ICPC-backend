from uuid import UUID


def build_workspace_key(
    contest_id: UUID,
    question_id: UUID,
    contest_team_id: UUID | None = None,
    contest_team_member_id: UUID | None = None,
) -> str:
    if contest_team_member_id:
        return (
            f"contest_workspace:"
            f"{contest_id}:"
            f"member:"
            f"{contest_team_member_id}:"
            f"{question_id}"
        )

    return f"contest_workspace:{contest_id}:team:{contest_team_id}:{question_id}"


def get_contest_channel_key(contest_id: UUID) -> str:
    return f"contest:{contest_id}:events"
