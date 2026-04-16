"""
Mapper functions for student team operations and responses.

Centralizes all ORM-to-response and request-to-DTO transformations for student team operations.
Maintains consistency between API schemas and internal data models.

Mapper Organization:
    - Response Mappers: ORM → API Response Schemas
      - to_student_team_member_response() - TeamUser → member summary
      - to_student_team_response() - Team → detailed team response
      - to_student_teams_list_response() - Paginated team list
      - to_student_available_team_response() - Available team for joining
      - to_student_available_teams_list_response() - Paginated available teams
      - to_student_team_join_response() - Join operation response
      - to_student_team_create_response() - Create operation response
      - to_student_team_leave_response() - Leave operation response
      - to_student_team_add_member_response() - Add member operation response
      - to_student_team_remove_member_response() - Remove member operation response

Key Principles:
    - Pure functions: No side effects, deterministic outputs
    - Type safety: Explicit parameter and return types
    - Documentation: Comprehensive docstrings with contexts
    - Reusability: Share common transformation logic
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.schema.student.teams import (
    StudentLeaveTeamResponse,
    StudentTeamAddMemberResponse,
    StudentTeamAvailableResponse,
    StudentTeamCreateAndJoinResponse,
    StudentTeamCreateResponse,
    StudentTeamJoinResponse,
    StudentTeamListResponse,
    StudentTeamMemberResponse,
    StudentTeamRemoveMemberResponse,
    StudentTeamResponse,
)
from app.utils.enums import UserRole

if TYPE_CHECKING:
    from app.models.contest import ContestTeam
    from app.models.team import Team, TeamUser
    from app.models.user import User
    from app.repositories.dto import PaginatedResult


# Response Mappers: ORM → API Schemas


def to_student_team_member_response(
    team_user: "TeamUser",
    team_leader_id: UUID | None = None,
) -> StudentTeamMemberResponse:
    """
    Map TeamUser ORM to student team member response.
    
    Transforms team membership relationship to member summary.
    Shows member identity and leadership status.
    
    Includes:
        - User identity (id, name, email)
        - Leadership status in team
    
    Excludes:
        - Role information (hidden from student view)
        - Internal user_id or other sensitive fields
    
    Args:
        team_user: TeamUser ORM linking user to team
        team_leader_id: UUID of team leader (determines is_leader flag)
    
    Returns:
        StudentTeamMemberResponse with member details
    """
    is_leader = team_leader_id is not None and team_user.user_id == team_leader_id
    return StudentTeamMemberResponse(
        id=team_user.user_id,
        name=team_user.user.name,
        email=team_user.user.email,
        is_leader=is_leader,
    )


def to_student_team_response(
    team: "Team",
    team_members: list["TeamUser"],
    current_user_id: UUID,
) -> StudentTeamResponse:
    """
    Map Team ORM and members to detailed team response.
    
    Used in GET /students/teams/{id} and team list endpoints.
    
    Transformation Process:
        1. Convert all team members to member responses
        2. Determine current user's role in team
        3. Calculate team size from member count
        4. Map team metadata to response
    
    Includes:
        - Team identity and metadata
        - Complete member list with roles
        - Current user's relationship to team (is_member, is_leader)
    
    Args:
        team: Team ORM object from database
        team_members: List of TeamUser objects in this team
        current_user_id: UUID of requesting user
    
    Returns:
        StudentTeamResponse with team details and full member list
    """
    members = [to_student_team_member_response(tu, team.leader_id) for tu in team_members]
    
    # Determine current user's role in team
    current_user_membership = next(
        (tu for tu in team_members if tu.user_id == current_user_id),
        None,
    )
    is_leader = team.leader_id == current_user_id if current_user_membership else False
    is_member = current_user_membership is not None
    
    return StudentTeamResponse(
        id=team.id,
        name=team.name,
        description=team.description,
        created_by=team.created_by,
        leader_id=team.leader_id,
        team_size=len(members),
        members=members,
        created_at=team.created_at,
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
    Map paginated Team results to paginated list response.
    
    Used in GET /students/teams/my-teams endpoint with pagination.
    
    Transformation Process:
        1. Extract Team objects from PaginatedResult
        2. Map each team with eager-loaded members to detail response
        3. Calculate pagination metadata
    
    Args:
        paginated_result: PaginatedResult containing Team ORM objects
        skip: Number of items skipped (0-based offset)
        limit: Number of items per page
        current_user_id: UUID of requesting user
    
    Returns:
        StudentTeamListResponse with paginated team list
    """
    teams = [
        to_student_team_response(team, team.members, current_user_id)
        for team in paginated_result.items
    ]
    
    total = paginated_result.total
    has_more = (skip + limit) < total
    current_page = (skip // limit) + 1 if limit > 0 else 1
    
    return StudentTeamListResponse(
        teams=teams,
        total=total,
        page=current_page,
        page_size=limit,
        has_more=has_more,
    )


def to_student_available_team_response(
    team: "Team",
    team_members: list["TeamUser"],
    current_user_id: UUID,
    max_team_size: int,
) -> StudentTeamAvailableResponse:
    """
    Map Team ORM to available team response for joining.
    
    Transforms team into summary for available teams list.
    Shows team details, availability slots, and joinability.
    
    Used in GET /students/contests/{id}/teams/available endpoint.
    
    Includes:
        - Team identity (id, name, description)
        - Leader information
        - Membership status (current size, max size)
        - Availability calculation
    
    Args:
        team: Team ORM object from database
        team_members: List of TeamUser objects in this team
        current_user_id: UUID of requesting user
        max_team_size: Maximum allowed team size in contest
    
    Returns:
        StudentTeamAvailableResponse with availability info
    """
    current_member_count = len(team_members)
    available_slots = max(0, max_team_size - current_member_count)
    
    # Get team leader name
    leader_user = next(
        (tu.user for tu in team_members if tu.user_id == team.leader_id),
        None,
    )
    
    return StudentTeamAvailableResponse(
        id=team.id,
        name=team.name,
        description=team.description,
        leader_name=leader_user.name if leader_user else "Unknown",
        current_size=current_member_count,
        max_size=max_team_size,
        available_slots=available_slots,
        created_at=team.created_at,
    )


def to_student_available_teams_list_response(
    teams: list["Team"],
    max_team_size: int,
    current_user_id: UUID,
) -> StudentTeamListResponse:
    """
    Map Team ORM list to available teams list response.
    
    Used in GET /students/contests/{id}/teams/available endpoint.
    
    Transformation Process:
        1. Convert each team to available team response
        2. Include availability calculations
        3. Return list without pagination metadata
    
    Args:
        teams: List of Team ORM objects with available slots
        max_team_size: Maximum team size in contest
        current_user_id: UUID of requesting user
    
    Returns:
        StudentTeamListResponse with available teams (simplified pagination)
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


# Operation Response Mappers


def to_student_team_create_response(
    team_id: UUID,
    team_name: str,
) -> StudentTeamCreateResponse:
    """
    Map team creation data to create response.
    
    Used in POST /students/contests/{id}/teams endpoint.
    Confirms team creation with team details.
    
    Args:
        team_id: UUID of newly created team
        team_name: Name of created team
    
    Returns:
        StudentTeamCreateResponse confirming creation
    """
    return StudentTeamCreateResponse(
        team_id=team_id,
        team_name=team_name,
        message="Team created successfully",
        status="success",
    )


def to_student_team_join_response(
    team_id: UUID,
    team_name: str,
    contest_id: UUID,
) -> StudentTeamJoinResponse:
    """
    Map team join data to join response.
    
    Used in POST /students/contests/{id}/teams/{team_id}/join endpoint.
    Confirms team join with team and contest details.
    
    Args:
        team_id: UUID of joined team
        team_name: Name of joined team
        contest_id: UUID of contest team belongs to
    
    Returns:
        StudentTeamJoinResponse confirming join
    """
    return StudentTeamJoinResponse(
        message=f"Successfully joined team '{team_name}'",
        team_id=team_id,
        contest_id=contest_id,
        status="success",
        approval_status=None,  # Set by service based on contest mode
    )


def to_student_team_leave_response(
    team_id: UUID,
) -> StudentLeaveTeamResponse:
    """
    Map team leave data to leave response.
    
    Used in DELETE /students/teams/{id}/members/me endpoint.
    Confirms student has left the team.
    
    Args:
        team_id: UUID of team being left
    
    Returns:
        StudentLeaveTeamResponse confirming departure
    """
    return StudentLeaveTeamResponse(
        message="You have left the team",
        team_id=team_id,
        status="success",
    )


def to_student_team_add_member_response(
    team_id: UUID,
    added_count: int,
    total_count: int,
    members: list[StudentTeamMemberResponse],
) -> StudentTeamAddMemberResponse:
    """
    Map member addition data to add member response.
    
    Used in POST /students/teams/{id}/members endpoint.
    Confirms members added and returns updated member list.
    
    Args:
        team_id: UUID of team
        added_count: Number of members added in operation
        total_count: Total members in team after addition
        members: Updated full member list
    
    Returns:
        StudentTeamAddMemberResponse with updated team member list
    """
    return StudentTeamAddMemberResponse(
        message=f"Successfully added {added_count} member(s) to team",
        team_id=team_id,
        added_count=added_count,
        total_member_count=total_count,
        members=members,
        status="success",
    )


def to_student_team_remove_member_response(
    team_id: UUID,
    removed_user_id: UUID,
) -> StudentTeamRemoveMemberResponse:
    """
    Map member removal data to remove member response.
    
    Used in DELETE /students/teams/{id}/members/{user_id} endpoint.
    Confirms member was removed from team.
    
    Args:
        team_id: UUID of team
        removed_user_id: UUID of removed user
    
    Returns:
        StudentTeamRemoveMemberResponse confirming removal
    """
    return StudentTeamRemoveMemberResponse(
        message="Member removed from team",
        team_id=team_id,
        removed_user_id=removed_user_id,
        status="success",
    )


def to_student_team_create_and_join_response(
    team_id: UUID,
    team_name: str,
    contest_id: UUID,
) -> StudentTeamCreateAndJoinResponse:
    """
    Map team creation and join data to combined response.
    
    Used in POST /students/teams/create-and-join endpoint (if exists).
    Combines team creation and automatic membership in single response.
    
    Args:
        team_id: UUID of newly created team
        team_name: Name of created team
        contest_id: UUID of contest team created for
    
    Returns:
        StudentTeamCreateAndJoinResponse confirming both operations
    """
    return StudentTeamCreateAndJoinResponse(
        message="Team created and you have been added as leader",
        team_id=team_id,
        contest_id=contest_id,
        team_name=team_name,
        approval_status=None,  # Set by service based on contest mode
        you_are_leader=True,
    )


# END OF FILE - All mapper functions completed above


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
