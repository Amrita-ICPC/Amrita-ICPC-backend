from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class TeamBase(BaseModel):
    """Base schema for team"""
    name: str = Field(..., min_length=1, max_length=255, description="Team name")
    description: Optional[str] = Field(None, description="Team description")
    logo: Optional[str] = Field(None, description="Team logo URL or data")

class TeamCreate(TeamBase):
    """Schema for creating a new team"""
    pass

class TeamUpdate(BaseModel):
    """Schema for updating a team"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    logo: Optional[str] = None

class TeamResponse(TeamBase):
    """Schema for team response"""
    id: UUID
    created_at: datetime = Field(..., description="Team creation timestamp")
    updated_at: datetime = Field(..., description="Team last update timestamp")
    
    model_config = ConfigDict(from_attributes=True)

class UserTeamResponse(BaseModel):
    """Schema for user in team context"""
    id: UUID
    email: str
    name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class AddTeamMemberRequest(BaseModel):
    """Schema for adding a member to the team"""
    user_id: UUID = Field(..., description="User ID to add to team")

class RemoveTeamMemberRequest(BaseModel):
    """Schema for removing a member from the team"""
    user_id: UUID = Field(..., description="User ID to remove from team")

class AddTeamMemberResponse(BaseModel):
    """Response after adding member to team"""
    message: str
    user_id: UUID
    team_id: UUID
    added_at: datetime

class RemoveTeamMemberResponse(BaseModel):
    """Response after removing member from team"""
    message: str
    user_id: UUID
    team_id: UUID
    removed_at: datetime

class MessageResponse(BaseModel):
    """Schema for message response."""

    message: str = Field(..., description="Response message")

class TeamListResponse(BaseModel):
    """Schema for paginated team list response"""
    total: int = Field(..., description="Total number of teams")
    teams: List[TeamResponse] = Field(..., description="List of teams")

class UserTeamListResponse(BaseModel):
    """Schema for user's team list response"""
    total: int = Field(..., description="Total number of teams")
    teams: List[TeamResponse] = Field(..., description="List of teams")
