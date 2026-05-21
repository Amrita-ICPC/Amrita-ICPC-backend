"""
Student-facing team schemas for API responses and requests.

These schemas expose team cards and membership overviews optimized for display in student dashboards and cards.
"""

from datetime import datetime
from typing import List, Optional, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import (
    TeamApprovalStatus,
    TeamInvitationStatus,
    InvitationType,
    TeamMemberRole,
    UserRole,
)

from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class StudentTeamMemberSummaryResponse(BaseModel):
    """Schema representing a team member's summary for display in the avatar stack."""

    id: UUID = Field(..., description="Unique identifier of the member")
    name: str = Field(..., description="Full name of the member")
    logo: Optional[str] = Field(
        None, description="Avatar/logo URL of the member's profile image"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentTeamCardResponse(BaseModel):
    """Schema representing a student team card with a membership overview."""

    id: UUID = Field(..., description="Unique identifier of the team")
    title: str = Field(..., description="Name or title of the team")
    description: Optional[str] = Field(None, description="Description of the team")
    logo: Optional[str] = Field(None, description="Logo/avatar URL of the team")
    created_at: datetime = Field(..., description="Timestamp of team creation")
    updated_at: datetime = Field(..., description="Timestamp of last team update")

    # Roles and Member Metrics
    is_leader: bool = Field(
        ..., description="Whether the requesting student is the leader of this team"
    )
    member_count: int = Field(
        ..., description="Total count of members currently in the team"
    )
    is_public: bool = Field(..., description="Whether the team is public")
    code: str = Field(..., description="The unique 6-digit random code of the team")
    has_requested: bool = Field(..., description="Whether the requesting student has a pending join request")

    # Avatar Stack Helper Fields
    members: List[StudentTeamMemberSummaryResponse] = Field(
        ...,
        max_length=3,
        description="List of up to the first 3 members to display in the UI avatar stack",
    )
    has_more_members: bool = Field(
        ...,
        description="Indicates whether the team has more than 3 members (i.e. if a '+X' bubble is needed)",
    )
    more_members_count: int = Field(
        ...,
        description="The count of additional members beyond the first 3 (e.g. 2 for a team of 5)",
    )

    model_config = ConfigDict(from_attributes=True)


class StudentTeamListResponse(BaseModel):
    """Schema representing a list of student team cards with pagination metadata."""

    teams: List[StudentTeamCardResponse] = Field(..., description="List of team cards")
    total: int = Field(..., description="Total count of teams matching filters")
    skip: int = Field(..., description="Number of items skipped")
    limit: int = Field(..., description="Maximum number of items returned")
    pending_invitation_count: int = Field(..., description="Total count of pending invitations for this student")
    pending_request_count: int = Field(..., description="Total count of pending join requests for teams led by this student")

    model_config = ConfigDict(from_attributes=True)


class StudentTeamsResponse(BaseModel):
    """Schema representing the list of teams and pending invitation count."""

    teams: List[StudentTeamCardResponse] = Field(..., description="List of team cards")
    pending_invitation: int = Field(..., description="Total count of pending invitations for this student")
    pending_request: int = Field(..., description="Total count of pending join requests for teams led by this student")

    model_config = ConfigDict(from_attributes=True)




class StudentTeamCreateRequest(BaseModel):
    """Schema representing the request to create a student team."""

    name: str = Field(..., min_length=3, max_length=100, description="The name of the team")
    description: Optional[str] = Field(None, max_length=500, description="Description of the team")
    is_public: bool = Field(default=True, description="Whether the team is public")


class StudentTeamUpdateRequest(BaseModel):
    """Schema representing the request to update/edit a student team."""

    name: Optional[str] = Field(None, min_length=3, max_length=100, description="The new name of the team")
    description: Optional[str] = Field(None, max_length=500, description="The new description of the team")
    is_public: Optional[bool] = Field(None, description="Whether the team is public")


class StudentTeamInvitationResponse(BaseModel):
    """Schema representing a team invitation, with team metadata but without full member details."""

    id: UUID = Field(..., description="Unique identifier of the invitation")
    team_id: UUID = Field(..., description="Unique identifier of the team being invited to")
    title: str = Field(..., description="Name or title of the team")
    description: Optional[str] = Field(None, description="Description of the team")
    logo: Optional[str] = Field(None, description="Logo/avatar URL of the team")
    created_at: datetime = Field(..., description="Timestamp of the invitation creation")
    updated_at: datetime = Field(..., description="Timestamp of the last invitation update")
    member_count: int = Field(..., description="Total count of members currently in the team")
    invited_by_name: str = Field(..., description="Name of the user who sent the invitation")
    invitation_type: InvitationType = Field(..., description="The type of invitation: INVITE or REQUEST")

    model_config = ConfigDict(from_attributes=True)


class StudentTeamInvitationListResponse(BaseModel):
    """Schema representing a list of team invitations."""

    invitations: List[StudentTeamInvitationResponse] = Field(..., description="List of invitations")
    total: int = Field(..., description="Total count of active invitations")

    model_config = ConfigDict(from_attributes=True)


class StudentTeamInvitationUpdateRequest(BaseModel):
    """Schema representing the request to accept, reject, or cancel a team invitation."""

    status: Literal[
        TeamInvitationStatus.ACCEPTED,
        TeamInvitationStatus.REJECTED,
        TeamInvitationStatus.CANCELLED,
    ] = Field(
        ...,
        description="The action status for the invitation, must be ACCEPTED, REJECTED, or CANCELLED",
    )

    model_config = ConfigDict(from_attributes=True)


class StudentTeamTransferLeaderRequest(BaseModel):
    """Schema representing the request to transfer team leadership to another member."""

    new_leader_id: UUID = Field(
        ...,
        description="The UUID of the team member to transfer leadership to",
    )

    model_config = ConfigDict(from_attributes=True)


class TeamMemberDetailResponse(BaseModel):
    """Schema representing detailed information of a team member."""

    id: UUID = Field(..., description="Unique identifier of the member")
    name: str = Field(..., description="Full name of the member")
    email: str = Field(..., description="Email address of the member")
    phone_no: Optional[str] = Field(None, description="Phone number of the member")
    gender: Optional[str] = Field(None, description="Gender of the member")
    role: UserRole = Field(..., description="Global role of the user")
    team_role: TeamMemberRole = Field(
        ..., description="Role of the member within this team (LEADER or MEMBER)"
    )
    joined_at: datetime = Field(
        ..., description="Timestamp when the member joined the team"
    )
    is_in_contest: Optional[bool] = Field(
        None, description="Whether the member is already registered in the specified contest"
    )

    model_config = ConfigDict(from_attributes=True)

