"""
Student-facing team schemas for API responses.

These schemas expose limited information about teams from a student's perspective,
focusing on team membership, availability, and participation status.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import TeamApprovalStatus, TeamStatus


class StudentTeamMemberResponse(BaseModel):
    """Schema for a team member (student view)."""

    id: UUID = Field(..., description="User/member unique identifier")
    name: str = Field(..., description="Member name")
    email: str = Field(..., description="Member email")
    is_leader: bool = Field(..., description="Whether this member is team leader")

    model_config = ConfigDict(from_attributes=True)


class StudentTeamResponse(BaseModel):
    """Schema for team details (GET /students/teams/{id} and GET /students/teams/my-teams)."""

    id: UUID = Field(..., description="Team unique identifier")
    name: str = Field(..., description="Team name")
    description: Optional[str] = Field(None, description="Team description")
    created_by: UUID = Field(..., description="User ID who created the team")
    leader_id: UUID = Field(..., description="Team leader user ID")
    team_size: int = Field(..., description="Number of members in team")
    members: List[StudentTeamMemberResponse] = Field(
        default_factory=list, description="List of team members"
    )
    created_at: datetime = Field(..., description="Team creation time (UTC)")
    is_leader: bool = Field(
        ..., description="Whether current user is team leader"
    )
    is_member: bool = Field(
        ..., description="Whether current user is team member"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentTeamAvailableResponse(BaseModel):
    """Schema for available team to join (GET /students/contests/{id}/teams/available)."""

    id: UUID = Field(..., description="Team unique identifier")
    name: str = Field(..., description="Team name")
    description: Optional[str] = Field(None, description="Team description")
    leader_name: str = Field(..., description="Team leader name")
    current_size: int = Field(..., description="Current number of team members")
    max_size: int = Field(..., description="Maximum team size allowed")
    available_slots: int = Field(..., description="Number of available slots")
    created_at: datetime = Field(..., description="Team creation time (UTC)")

    model_config = ConfigDict(from_attributes=True)


class StudentTeamJoinResponse(BaseModel):
    """Schema for join team response (POST /students/contests/{id}/teams/join)."""

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


class StudentTeamCreateRequest(BaseModel):
    """Schema for creating a new team (POST /students/contests/{id}/teams)."""

    name: str = Field(..., min_length=1, max_length=255, description="Team name")
    description: Optional[str] = Field(None, max_length=1000, description="Team description")
    contest_id: UUID = Field(..., description="Contest UUID to create team for")

    model_config = ConfigDict(from_attributes=True)


class StudentTeamJoinRequest(BaseModel):
    """Schema for joining an existing team (POST /students/contests/{contest_id}/teams/{team_id}/join)."""

    pass  # No additional fields needed - team_id comes from URL path, user_id from auth


class StudentTeamCreateAndJoinResponse(BaseModel):
    """Schema for create and join team response (POST /students/teams/create-and-join)."""

    message: str = Field(..., description="Operation status message")
    team_id: UUID = Field(..., description="Newly created team ID")
    contest_id: UUID = Field(..., description="Contest ID")
    team_name: str = Field(..., description="Team name")
    approval_status: TeamApprovalStatus = Field(
        ..., description="Team approval status in contest (WAITING or APPROVED)"
    )
    you_are_leader: bool = Field(..., description="Whether you are team leader")

    model_config = ConfigDict(from_attributes=True)


class StudentLeaveTeamResponse(BaseModel):
    """Schema for leave team response (DELETE /students/teams/{id}/members/me)."""

    message: str = Field(..., description="Leave status message")
    team_id: UUID = Field(..., description="Team ID")
    status: str = Field(
        ..., description="Leave status (success, cannot_leave_leader, not_member)"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentTeamAddMemberRequest(BaseModel):
    """Schema for adding a member to team (POST /students/teams/{id}/members/add)."""

    user_email: str = Field(
        ..., 
        description="Email of the user to add to team"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentTeamAddMemberResponse(BaseModel):
    """Schema for add member response (POST /students/teams/{id}/members/add)."""

    message: str = Field(..., description="Operation status message")
    team_id: UUID = Field(..., description="Team ID")
    added_user_email: str = Field(..., description="Email of added user")
    new_member_count: int = Field(..., description="New total member count")
    status: str = Field(
        ..., description="Add status (success, already_member, team_full, user_not_found)"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentTeamRemoveMemberRequest(BaseModel):
    """Schema for removing a member from team (DELETE /students/teams/{id}/members/{user_id})."""

    pass  # user_id comes from URL path


class StudentTeamRemoveMemberResponse(BaseModel):
    """Schema for remove member response (DELETE /students/teams/{id}/members/{user_id})."""

    message: str = Field(..., description="Operation status message")
    team_id: UUID = Field(..., description="Team ID")
    removed_user_email: str = Field(..., description="Email of removed user")
    new_member_count: int = Field(..., description="New total member count")
    status: str = Field(
        ..., description="Remove status (success, not_member, cannot_remove_leader)"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentTeamListResponse(BaseModel):
    """Schema for list of student's teams (GET /students/teams/my-teams)."""

    teams: List[StudentTeamResponse] = Field(..., description="List of teams user is member of")
    total_teams: int = Field(..., description="Total number of teams")

    model_config = ConfigDict(from_attributes=True)
