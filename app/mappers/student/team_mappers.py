from uuid import UUID
from typing import List, Tuple
from datetime import datetime

from app.models.user import User
from app.models.team import Team, TeamInvitation
from app.utils.enums import TeamMemberRole
from app.schema.student.teams import (
    StudentTeamCardResponse,
    StudentTeamMemberSummaryResponse,
    StudentTeamListResponse,
    StudentTeamInvitationResponse,
    StudentTeamInvitationListResponse,
    TeamMemberDetailResponse,
)


def to_student_team_card_response(
    team: Team,
    user_id: UUID,
    has_requested: bool = False,
) -> StudentTeamCardResponse:
    """Map a Team database ORM model to a StudentTeamCardResponse schema.

    Args:
        team: The Team database ORM model to map.
        user_id: UUID of the requesting student user.
        has_requested: Whether the requesting student has a pending join request.

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
        is_public=team.is_public,
        code=team.code,
        has_requested=has_requested,
    )


def to_student_team_list_response(
    teams: List[Team],
    total: int,
    skip: int,
    limit: int,
    user_id: UUID,
    pending_invitation_count: int = 0,
    pending_request_count: int = 0,
    requested_team_ids: set[UUID] | None = None,
) -> StudentTeamListResponse:
    """Map a list of Team ORM models to a StudentTeamListResponse with pagination.

    Args:
        teams: List of Team ORM database models.
        total: Total number of records matching the filters.
        skip: Offset skipped records.
        limit: Max items returned.
        user_id: UUID of the requesting student user.
        pending_invitation_count: Total count of pending invitations for this student.
        pending_request_count: Total count of pending join requests for teams led by this student.
        requested_team_ids: Set of team IDs with pending requests from the user.

    Returns:
        StudentTeamListResponse: Standard paginated response.
    """
    if requested_team_ids is None:
        requested_team_ids = set()
    team_cards = [
        to_student_team_card_response(team, user_id, team.id in requested_team_ids)
        for team in teams
    ]
    return StudentTeamListResponse(
        teams=team_cards,
        total=total,
        skip=skip,
        limit=limit,
        pending_invitation_count=pending_invitation_count,
        pending_request_count=pending_request_count,
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
        created_at=invitation.sent_at,
        updated_at=invitation.updated_at,
        member_count=len(invitation.team.members),
        invited_by_name=invitation.sender.name,
        invitation_type=invitation.invitation_type,
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


def to_team_member_detail_responses(
    members_data: List[Tuple[User, TeamMemberRole, datetime, bool | None]],
) -> List[TeamMemberDetailResponse]:
    """Map a list of team members data tuples to a list of TeamMemberDetailResponse schemas.

    Args:
        members_data: List of tuples (User, TeamMemberRole, joined_at, is_in_contest).

    Returns:
        List[TeamMemberDetailResponse]: List of mapped detailed team member schemas.
    """
    return [
        TeamMemberDetailResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            phone_no=user.phone_no,
            gender=user.gender,
            role=user.role,
            team_role=team_role,
            joined_at=joined_at,
            is_in_contest=is_in_contest,
        )
        for user, team_role, joined_at, is_in_contest in members_data
    ]


