"""Mapper functions for student team responses.

Transforms ORM Team objects and repository data into student-facing API response schemas.
Centralizes all team response building logic in one place for easy maintenance and reusability.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.schema.student.teams import (
    StudentLeaveTeamResponse,
    StudentTeamAvailableResponse,
    StudentTeamCreateAndJoinResponse,
    StudentTeamCreateRequest,
    StudentTeamJoinResponse,
    StudentTeamListResponse,
    StudentTeamMemberResponse,
    StudentTeamResponse,
)
from app.utils.enums import UserRole

if TYPE_CHECKING:
    from app.models.contest import ContestTeam
    from app.models.team import Team, TeamUser
    from app.models.user import User
    from app.repositories.dto import PaginatedResult


def to_student_team_member_response(team_user: "TeamUser") -> StudentTeamMemberResponse:
    """
    Convert TeamUser ORM object to StudentTeamMemberResponse.
    
    Maps a team user relationship to member info visible to other students.
    Excludes sensitive fields but includes leadership status.
    
    Args:
        team_user: TeamUser ORM object linking user to team
    
    Returns:
        StudentTeamMemberResponse with member details
    """
    return StudentTeamMemberResponse(
        user_id=team_user.user_id,
        name=team_user.user.name,
        email=team_user.user.email,
        is_leader=team_user.is_leader,
    )


def to_student_team_response(
    team: "Team",
    team_members: list["TeamUser"],
    current_user_id: UUID,
) -> StudentTeamResponse:
    """
    Convert Team ORM and members to StudentTeamResponse.
    
    Maps a team to response including member list and current user's role in team.
    Used for detailed team view and team list endpoints.
    
    Args:
        team: Team ORM object
        team_members: List of TeamUser objects in this team
        current_user_id: UUID of requesting user (to determine role)
    
    Returns:
        StudentTeamResponse with team and member details
    """
    members = [to_student_team_member_response(tu) for tu in team_members]
    
    # Find current user's role in team
    current_user_membership = next(
        (tu for tu in team_members if tu.user_id == current_user_id),
        None,
    )
    is_leader = current_user_membership.is_leader if current_user_membership else False
    is_member = current_user_membership is not None
    
    return StudentTeamResponse(
        id=team.id,
        name=team.name,
        created_by=team.created_by,
        created_at=team.created_at,
        updated_at=team.updated_at,
        members=members,
        member_count=len(members),
        is_leader=is_leader,
        is_member=is_member,
    )


def to_student_teams_list_response(
    paginated_result: "PaginatedResult",
    skip: int,
    limit: int,
    current_user_id: UUID,
) -> StudentTeamListResponse:
    """
    Convert paginated Team results to StudentTeamListResponse.
    
    Args:
        paginated_result: PaginatedResult containing tuples of (Team, list[TeamUser])
        skip: Number of items skipped (for pagination info)
        limit: Limit used in query (for pagination info)
        current_user_id: UUID of requesting user
    
    Returns:
        StudentTeamListResponse with pagination and team list
    """
    teams = [
        to_student_team_response(team, team_members, current_user_id)
        for team, team_members in paginated_result.items
    ]
    
    total = paginated_result.total
    has_more = (skip + limit) < total
    
    return StudentTeamListResponse(
        teams=teams,
        total=total,
        page=(skip // limit) + 1 if limit > 0 else 1,
        page_size=limit,
        has_more=has_more,
    )


def to_student_available_teams_list_response(
    teams: list["Team"],
    max_team_size: int,
    current_user_id: UUID,
) -> StudentTeamListResponse:
    """
    Convert list of Team objects to StudentTeamListResponse for available teams.
    
    Transforms Team ORM objects into available team responses with:
    - Team details and members
    - Availability slot calculation
    - User's ability to join
    
    Args:
        teams: List of Team ORM objects with available slots
        max_team_size: Maximum team size in contest
        current_user_id: UUID of requesting user
    
    Returns:
        StudentTeamListResponse with available teams list
    """
    team_responses = [
        to_student_available_team_response(
            team,
            team.members,
            current_user_id,
            max_team_size,
        )
        for team in teams
    ]
    
    return StudentTeamListResponse(
        teams=team_responses,
        total=len(teams),
        page=1,
        page_size=len(teams),
        has_more=False,
    )


def to_student_available_team_response(
    team: "Team",
    team_members: list["TeamUser"],
    current_user_id: UUID,
    max_team_size: int,
) -> StudentTeamAvailableResponse:
    """
    Convert Team ORM to StudentTeamAvailableResponse.
    
    Maps a team available for joining to response including:
    - Member list and current size
    - Available slots calculation (max_team_size - current_members)
    - Whether current user can join
    
    Args:
        team: Team ORM object
        team_members: List of TeamUser objects in this team
        current_user_id: UUID of requesting user
        max_team_size: Maximum team size in contest
    
    Returns:
        StudentTeamAvailableResponse with availability info
    """
    members = [to_student_team_member_response(tu) for tu in team_members]
    current_member_count = len(members)
    available_slots = max(0, max_team_size - current_member_count)
    
    is_already_member = any(tu.user_id == current_user_id for tu in team_members)
    
    return StudentTeamAvailableResponse(
        id=team.id,
        name=team.name,
        created_by=team.created_by,
        created_at=team.created_at,
        members=members,
        member_count=current_member_count,
        available_slots=available_slots,
        can_join=available_slots > 0 and not is_already_member,
        is_already_member=is_already_member,
    )


def to_student_available_teams_list_response(
    teams: list["Team"],
    max_team_size: int,
    current_user_id: UUID,
) -> StudentTeamListResponse:
    """
    Convert list of Team objects to StudentTeamListResponse for available teams.
    
    Transforms Team ORM objects into available team responses with:
    - Team details and members
    - Availability slot calculation
    - User's ability to join
    
    Args:
        teams: List of Team ORM objects with available slots
        max_team_size: Maximum team size in contest
        current_user_id: UUID of requesting user
    
    Returns:
        StudentTeamListResponse with available teams list
    """
    team_responses = [
        to_student_available_team_response(
            team,
            team.members,
            current_user_id,
            max_team_size,
        )
        for team in teams
    ]
    
    return StudentTeamListResponse(
        teams=team_responses,
        total=len(teams),
        page=1,
        page_size=len(teams),
        has_more=False,
    )


def to_student_team_response(
    team: "Team",
    team_members: list["TeamUser"],
    current_user_id: UUID,
) -> StudentTeamResponse:
    """
    Convert Team ORM to StudentTeamResponse.
    
    Args:
        team: Team ORM object
        team_members: List of TeamUser objects in this team
        current_user_id: UUID of requesting user
    
    Returns:
        StudentTeamResponse ready for API response
    """
    members = [to_student_team_member_response(tu) for tu in team_members]
    is_leader = any(tu.user_id == current_user_id and tu.is_leader for tu in team_members)
    
    return StudentTeamResponse(
        id=team.id,
        name=team.name,
        created_by=team.created_by,
        created_at=team.created_at,
        leader=members[0] if members and any(tu.is_leader for tu in team_members) else None,
        members=members,
        member_count=len(members),
        is_leader=is_leader,
    )


def to_student_team_join_response(
    team: "Team",
    user_id: UUID,
    joined_at=None,
) -> StudentTeamJoinResponse:
    """
    Convert Team and join info to StudentTeamJoinResponse.
    
    Response confirming successful team join operation.
    
    Args:
        team: Team ORM object user joined
        user_id: UUID of joined user
        joined_at: Timestamp of join (optional)
    
    Returns:
        StudentTeamJoinResponse with join confirmation
    """
    return StudentTeamJoinResponse(
        team_id=team.id,
        team_name=team.name,
        user_id=user_id,
        status="joined",
        message=f"Successfully joined team '{team.name}'",
    )


def to_student_team_create_and_join_response(
    team: "Team",
    contest_team: "ContestTeam",
    user_id: UUID,
) -> StudentTeamCreateAndJoinResponse:
    """
    Convert Team and ContestTeam info to StudentTeamCreateAndJoinResponse.
    
    Response confirming successful team creation and self-join.
    Acts as team leader after creation.
    
    Args:
        team: Newly created Team ORM object
        contest_team: ContestTeam record created for registration
        user_id: UUID of creating user (team leader)
    
    Returns:
        StudentTeamCreateAndJoinResponse with creation and join confirmation
    """
    return StudentTeamCreateAndJoinResponse(
        team_id=team.id,
        contest_id=contest_team.contest_id,
        team_name=team.name,
        approval_status=contest_team.approval_status,
        you_are_leader=True,
        message=f"Team '{team.name}' created and you are now the leader",
    )


def to_student_leave_team_response(
    team_id: UUID,
    team_name: str,
    user_id: UUID,
) -> StudentLeaveTeamResponse:
    """
    Convert leave operation data to StudentLeaveTeamResponse.
    
    Response confirming successful team leave operation.
    
    Args:
        team_id: UUID of team left
        team_name: Name of team left
        user_id: UUID of user who left
    
    Returns:
        StudentLeaveTeamResponse with leave confirmation
    """
    return StudentLeaveTeamResponse(
        team_id=team_id,
        team_name=team_name,
        user_id=user_id,
        status="left",
        message=f"Successfully left team '{team_name}'",
    )
