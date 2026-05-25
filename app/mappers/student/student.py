from app.models.contest import ContestTeamMember
from app.schema.user import (
    ContestInfoForInvitation,
    ContestTeamInfo,
    ContestTeamMemberInfo,
    UserInvitationResponse,
)
from app.utils.enums import ContestTeamMemberStatus, TeamMemberRole


def to_user_invitation_response(
    invitation: ContestTeamMember,
    registered_teams_count: int,
) -> UserInvitationResponse:
    """
    Maps a ContestTeamMember object to a UserInvitationResponse schema.
    """
    contest_team = invitation.contest_team
    contest = contest_team.contest

    can_accept = True
    if contest.max_teams is not None and contest.max_teams > 0:
        can_accept = registered_teams_count < contest.max_teams

    team_members = contest_team.contest_team_member
    accepted_members = [
        m for m in team_members if m.status == ContestTeamMemberStatus.ACCEPTED
    ]

    member_infos = []
    for member_record in accepted_members:
        user = member_record.user
        role = (
            TeamMemberRole.LEADER
            if contest_team.leader_id == user.id
            else TeamMemberRole.MEMBER
        )
        member_infos.append(
            ContestTeamMemberInfo(
                id=user.id,
                name=user.name,
                email=user.email,
                status=member_record.status,
                role=role,
            )
        )

    team_info = ContestTeamInfo(
        id=contest_team.id,
        name=contest_team.name,
        members=member_infos,
        joined_members_count=len(accepted_members),
    )

    contest_info = ContestInfoForInvitation(
        id=contest.id,
        name=contest.name,
        description=contest.description,
        image=contest.image,
        min_team_size=contest.min_team_size,
        max_team_size=contest.max_team_size,
        registered_teams_count=registered_teams_count,
    )

    return UserInvitationResponse(
        id=invitation.id,
        can_accept_invitation=can_accept,
        contest=contest_info,
        team=team_info,
    )
