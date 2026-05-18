from uuid import UUID
from typing import List

from app.models.team import Team, TeamInvitation
from app.schema.student.teams import (
    StudentTeamCardResponse,
    StudentTeamMemberSummaryResponse,
    StudentTeamListResponse,
    StudentTeamInvitationResponse,
    StudentTeamInvitationListResponse,
)


def to_student_team_card_response(team: Team, user_id: UUID) -> StudentTeamCardResponse:
    """Map a Team database ORM model to a StudentTeamCardResponse schema.

    Args:
        team: The Team database ORM model to map.
        user_id: UUID of the requesting student user.

    Returns:
        StudentTeamCardResponse: Mapped response card schema.
    """
    is_leader = team.leader_id == user_id

    member_list: List[StudentTeamMemberSummaryResponse] = []
    # Map the first 3 members for the UI avatar stack
    for tu in team.members[:3]:
        member_list.append(
            StudentTeamMemberSummaryResponse(
                id=tu.user_id,
                name=tu.user.name,
                logo=None,  # User profile logos not supported by the model currently
            )
        )

    total_count = len(team.members)
    has_more = total_count > 3
    more_count = total_count - 3 if has_more else 0

    return StudentTeamCardResponse(
        id=team.id,
        title=team.name,
        description=team.description,
        logo=team.logo,
        created_at=team.created_at,
        updated_at=team.updated_at,
        is_leader=is_leader,
        member_count=total_count,
        members=member_list,
        has_more_members=has_more,
        more_members_count=more_count,
    )


def to_student_team_list_response(
    teams: List[Team],
    total: int,
    skip: int,
    limit: int,
    user_id: UUID,
    pending_invitation_count: int = 0,
) -> StudentTeamListResponse:
    """Map a list of Team ORM models to a StudentTeamListResponse with pagination.

    Args:
        teams: List of Team ORM database models.
        total: Total number of records matching the filters.
        skip: Offset skipped records.
        limit: Max items returned.
        user_id: UUID of the requesting student user.
        pending_invitation_count: Total count of pending invitations for this student.

    Returns:
        StudentTeamListResponse: Standard paginated response.
    """
    team_cards = [to_student_team_card_response(team, user_id) for team in teams]
    return StudentTeamListResponse(
        teams=team_cards,
        total=total,
        skip=skip,
        limit=limit,
        pending_invitation_count=pending_invitation_count,
    )



def to_student_team_invitation_response(invitation: TeamInvitation) -> StudentTeamInvitationResponse:
    """Map a TeamInvitation database ORM model to a StudentTeamInvitationResponse schema.

    Args:
        invitation: The TeamInvitation database ORM model.

    Returns:
        StudentTeamInvitationResponse: Mapped invitation response schema.
    """
    return StudentTeamInvitationResponse(
        id=invitation.id,
        team_id=invitation.team_id,
        title=invitation.team.name,
        description=invitation.team.description,
        logo=invitation.team.logo,
        created_at=invitation.invited_at,
        updated_at=invitation.updated_at,
        member_count=len(invitation.team.members),
        invited_by_name=invitation.invited_by_user.name,
    )


def to_student_team_invitation_list_response(
    invitations: List[TeamInvitation],
    total: int,
) -> StudentTeamInvitationListResponse:
    """Map a list of TeamInvitation ORM models to a StudentTeamInvitationListResponse.

    Args:
        invitations: List of TeamInvitation database ORM models.
        total: Total number of active invitations.

    Returns:
        StudentTeamInvitationListResponse: Standard invitation list response.
    """
    mapped_invitations = [to_student_team_invitation_response(inv) for inv in invitations]
    return StudentTeamInvitationListResponse(
        invitations=mapped_invitations,
        total=total,
    )

