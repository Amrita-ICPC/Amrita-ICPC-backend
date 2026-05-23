from app.utils.enums import TeamStatus, ContestTeamMemberStatus
from app.exceptions.student.teams import (
    TeamStatusNotAllowedForUpdatingContestTeamMemberStatusException,
    InvalidContestTeamMemberStatusUpdateException,
)
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

class ContestTeamUpdate(BaseModel):
    """Schema for updating a contest team."""
    name: str = Field(..., description="The name of the team")

class ContestTeamLeaderTransfer(BaseModel):
    """Schema for transferring team leadership."""
    new_leader_id: UUID = Field(..., description="The ID of the new team leader")

class ContestTeamStatusUpdate(BaseModel):
    status: TeamStatus = Field(..., description="The status of the team")

class ContestTeamMemberStatusUpdate(BaseModel):
    """Schema for updating a contest team member status."""
    status: ContestTeamMemberStatus = Field(..., description="The status of the contest team member")


class ContestTeamInviteRequest(BaseModel):
    """Schema for inviting members to a contest team."""
    user_ids: list[UUID] = Field(..., description="List of user IDs to invite")

    