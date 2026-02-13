from typing import List, Optional
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.utils.enums import TeamStatus


class TeamCreate(BaseModel):
    """
    Schema for creating a new team.

    Attributes:
        name: Name of the team.
        description: Description of the team.
        logo: URL or path to the team logo.
        member_ids: List of user IDs to include in the team.
        status: Status of the team (default: DRAFT).
    """

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    logo: Optional[str] = None
    member_ids: List[UUID] = Field(default_factory=list)
    leader_id: Optional[UUID] = None
    status: TeamStatus = Field(default=TeamStatus.DRAFT)

    @model_validator(mode="after")
    def validate_leader(self) -> "TeamCreate":
        member_ids = self.member_ids
        leader_id = self.leader_id

        if member_ids and leader_id is None:
            raise ValueError("Leader ID is required when there are members.")

        if leader_id and leader_id not in member_ids:
            raise ValueError("Leader must be one of the members.")

        return self


class TeamResponse(BaseModel):
    """
    Schema for team response.

    Attributes:
        id: Unique identifier for the team.
        name: Name of the team.
        description: Description of the team.
        logo: Team logo.
        status: Team status.
    """

    id: UUID
    name: str
    description: Optional[str]
    logo: Optional[str]

    model_config = ConfigDict(from_attributes=True)
