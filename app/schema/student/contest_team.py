from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

class ContestTeamUpdate(BaseModel):
    """Schema for updating a contest team."""
    name: str = Field(..., description="The name of the team")