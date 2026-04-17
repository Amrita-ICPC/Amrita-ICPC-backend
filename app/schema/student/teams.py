"""
Student-facing team schemas for API responses and requests.

These schemas expose limited information about teams from a student's perspective,
focusing on team membership, availability, and participation status.

Hides internal team management details and restricts operations to student-appropriate actions.

Schema Organization:
    - Request Schemas: StudentTeamCreateRequest, StudentTeamJoinRequest, StudentTeamAddMemberRequest
    - Response Base Schemas: StudentTeamMemberResponse, StudentContestTeamResponse
    - Summary Responses: StudentTeamAvailableResponse
    - Detail Responses: StudentTeamResponse
    - Operation Responses: StudentTeamCreateResponse, StudentTeamJoinResponse, StudentLeaveTeamResponse
    - Member Management Responses: StudentTeamAddMemberResponse, StudentTeamRemoveMemberResponse
    - Collection Responses: StudentTeamListResponse
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import TeamApprovalStatus


# Request Schemas
class StudentTeamCreateRequest(BaseModel):
    """
    Schema for creating a new team in a contest.

    Student creates a team to participate in a contest.
    Creator becomes team leader and first member.

    Attributes:
        name: Name of the team (1-255 characters)
        description: Optional team description (max 1000 characters)
        contest_id: ID of the contest to create team for
    """

    name: str = Field(..., min_length=1, max_length=255, description="Team name")
    description: Optional[str] = Field(
        None, max_length=1000, description="Team description"
    )
    contest_id: UUID = Field(..., description="Contest UUID to create team for")

    model_config = ConfigDict(from_attributes=True)


class StudentTeamJoinRequest(BaseModel):
    """
    Schema for joining an existing team in a contest.

    Student requests to join an available team.
    Approval depends on contest's team_approval_mode.

    Attributes:
        contest_id: ID of the contest the team belongs to

    Note:
        team_id comes from URL path
        user_id comes from authentication context
    """

    contest_id: UUID = Field(..., description="Contest ID that team belongs to")

    model_config = ConfigDict(from_attributes=True)


class StudentTeamAddMemberRequest(BaseModel):
    """
    Schema for adding members to team (leader only).

    Follows the same pattern as TeamMemberAdd from instructor endpoints.
    Only team leader can perform this action.

    Attributes:
        member_ids: List of user IDs to add to team (minimum 1)
        leader_id: Optional new team leader (must be one of the members)
        contest_id: Contest ID that team belongs to
    """

    member_ids: List[UUID] = Field(
        ..., min_length=1, description="List of user IDs to add to team"
    )
    leader_id: Optional[UUID] = Field(
        None, description="New team leader (must be existing or new member)"
    )
    contest_id: UUID = Field(..., description="Contest ID that team belongs to")

    model_config = ConfigDict(from_attributes=True)


# Base Response Schemas
class StudentTeamMemberResponse(BaseModel):
    """
    Schema for a team member from student view.

    Represents a user in a team with essential information.
    Does not expose sensitive fields like internal IDs.

    Attributes:
        id: User/member unique identifier
        name: Member name
        email: Member email address
        is_leader: Whether this member is the team leader
    """

    id: UUID = Field(..., description="User/member unique identifier")
    name: str = Field(..., description="Member name")
    email: str = Field(..., description="Member email")
    is_leader: bool = Field(..., description="Whether this member is team leader")

    model_config = ConfigDict(from_attributes=True)


# Summary Response Schemas
class StudentTeamAvailableResponse(BaseModel):
    """
    Schema for available team to join in a contest.

    Used in GET /students/contests/{id}/teams/available endpoint.
    Shows teams with slots available for students to join.

    Attributes:
        id: Team unique identifier
        name: Team name
        description: Team description
        leader_name: Name of team leader
        current_size: Number of current members
        max_size: Maximum team size allowed
        available_slots: Number of available slots to join
        created_at: When team was created
    """

    id: UUID = Field(..., description="Team unique identifier")
    name: str = Field(..., description="Team name")
    description: Optional[str] = Field(None, description="Team description")
    leader_name: str = Field(..., description="Team leader name")
    current_size: int = Field(..., description="Current number of team members")
    max_size: int = Field(..., description="Maximum team size allowed")
    available_slots: int = Field(..., description="Number of available slots")
    created_at: datetime = Field(..., description="Team creation time (UTC)")

    model_config = ConfigDict(from_attributes=True)


# Detail Response Schemas
class StudentTeamResponse(BaseModel):
    """
    Schema for team details with members.

    Used in GET /students/teams/{id} and GET /students/teams/my-teams endpoints.
    Shows complete team information including member list and user's role.

    Attributes:
        id: Team unique identifier
        name: Team name
        description: Team description
        created_by: User ID who created the team
        leader_id: Team leader user ID
        team_size: Number of members in team
        members: List of team members
        created_at: Team creation time (UTC)
        is_leader: Whether current user is team leader
        is_member: Whether current user is team member
    """

    id: UUID = Field(..., description="Team unique identifier")
    name: str = Field(..., description="Team name")
    description: Optional[str] = Field(None, description="Team description")
    created_by: Optional[UUID] = Field(
        None,
        description="User ID who created the team (may be null if user was deleted)",
    )
    leader_id: Optional[UUID] = Field(
        None,
        description="Team leader user ID (may be null if user was deleted)",
    )
    team_size: int = Field(..., description="Number of members in team")
    members: List[StudentTeamMemberResponse] = Field(
        default_factory=list, description="List of team members"
    )
    created_at: datetime = Field(..., description="Team creation time (UTC)")
    is_leader: bool = Field(..., description="Whether current user is team leader")
    is_member: bool = Field(..., description="Whether current user is team member")

    model_config = ConfigDict(from_attributes=True)


# Operation Response Schemas
class StudentTeamCreateResponse(BaseModel):
    """
    Schema for create team operation response.

    Used in POST /students/contests/{id}/teams endpoint.
    Confirms team creation and provides team details.

    Attributes:
        team_id: Newly created team ID
        team_name: Team name
        message: Operation status message
        status: Create status (success, invalid_name, name_exists)
    """

    team_id: UUID = Field(..., description="Newly created team ID")
    team_name: str = Field(..., description="Team name")
    message: str = Field(..., description="Operation status message")
    status: str = Field(
        ..., description="Create status (success, invalid_name, name_exists)"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentTeamJoinResponse(BaseModel):
    """
    Schema for join team operation response.

    Used in POST /students/contests/{id}/teams/{team_id}/join endpoint.
    Confirms team join with status and approval info.

    Attributes:
        message: Join status message
        team_id: Team ID
        contest_id: Contest ID
        status: Join status (success, pending_approval, already_member, team_full)
        approval_status: Team approval status (WAITING or APPROVED)
    """

    message: str = Field(..., description="Join status message")
    team_id: UUID = Field(..., description="Team ID")
    contest_id: UUID = Field(..., description="Contest ID")
    status: str = Field(
        ...,
        description="Join status (success, pending_approval, already_member, team_full)",
    )
    approval_status: Optional[TeamApprovalStatus] = Field(
        None, description="Team approval status (WAITING or APPROVED)"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentLeaveTeamResponse(BaseModel):
    """
    Schema for leave team operation response.

    Used in DELETE /students/teams/{id}/members/me endpoint.
    Confirms student has left the team.

    Attributes:
        message: Leave status message
        team_id: Team ID
        status: Leave status (success, cannot_leave_leader, not_member)
    """

    message: str = Field(..., description="Leave status message")
    team_id: UUID = Field(..., description="Team ID")
    status: str = Field(
        ..., description="Leave status (success, cannot_leave_leader, not_member)"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentTeamCreateAndJoinResponse(BaseModel):
    """
    Schema for create and join team operation response.

    Used in POST /students/teams/create-and-join endpoint (if exists).
    Combines team creation and automatic join in single response.

    Attributes:
        message: Operation status message
        team_id: Newly created team ID
        contest_id: Contest ID
        team_name: Team name
        approval_status: Team approval status in contest
        you_are_leader: Whether you are the team leader
    """

    message: str = Field(..., description="Operation status message")
    team_id: UUID = Field(..., description="Newly created team ID")
    contest_id: UUID = Field(..., description="Contest ID")
    team_name: str = Field(..., description="Team name")
    approval_status: TeamApprovalStatus = Field(
        ..., description="Team approval status in contest (WAITING or APPROVED)"
    )
    you_are_leader: bool = Field(..., description="Whether you are team leader")

    model_config = ConfigDict(from_attributes=True)


# Member Management Response Schemas
class StudentTeamAddMemberResponse(BaseModel):
    """
    Schema for add members operation response.

    Used in POST /students/teams/{id}/members endpoint.
    Confirms members were added and shows updated team member list.

    Attributes:
        message: Operation status message
        team_id: Team ID
        added_count: Number of members added
        total_member_count: New total member count
        members: Updated list of team members
        status: Add status (success, team_full, invalid_size, user_not_found)
    """

    message: str = Field(..., description="Operation status message")
    team_id: UUID = Field(..., description="Team ID")
    added_count: int = Field(..., description="Number of members added")
    total_member_count: int = Field(..., description="New total member count")
    members: List[StudentTeamMemberResponse] = Field(
        ..., description="Updated list of team members"
    )
    status: str = Field(
        ..., description="Add status (success, team_full, invalid_size, user_not_found)"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentTeamRemoveMemberResponse(BaseModel):
    """
    Schema for remove member operation response.

    Used in DELETE /students/teams/{id}/members/{user_id} endpoint.
    Confirms member was removed from team.

    Attributes:
        message: Operation status message
        team_id: Team ID
        removed_user_id: ID of removed user
        status: Remove status (success, not_member, cannot_remove_leader)
    """

    message: str = Field(..., description="Operation status message")
    team_id: UUID = Field(..., description="Team ID")
    removed_user_id: UUID = Field(..., description="ID of removed user")
    status: str = Field(
        ..., description="Remove status (success, not_member, cannot_remove_leader)"
    )

    model_config = ConfigDict(from_attributes=True)


# Collection Response Schemas
class StudentTeamListResponse(BaseModel):
    """
    Schema for paginated list of teams.

    Used in GET /students/teams/my-teams and available teams endpoints.
    Returns list of teams with pagination info.

    Attributes:
        teams: List of teams (StudentTeamResponse or summary format)
        total: Total number of teams
        page: Current page number (optional for some list endpoints)
        page_size: Number of teams per page (optional for some endpoints)
        has_more: Whether there are more pages (optional for some endpoints)
    """

    teams: List[StudentTeamResponse | StudentTeamAvailableResponse] = Field(
        ..., description="List of teams"
    )
    total: int = Field(..., description="Total number of teams")
    page: Optional[int] = Field(None, description="Current page number")
    page_size: Optional[int] = Field(None, description="Number of teams per page")
    has_more: Optional[bool] = Field(None, description="Whether there are more pages")

    model_config = ConfigDict(from_attributes=True)
