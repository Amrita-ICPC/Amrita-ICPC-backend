from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import ContestResultVisibility


class LeaderboardRow(BaseModel):
    """A single row/entry in the contest leaderboard representing a team's standing."""

    rank: int = Field(..., description="Current rank of the team")
    team_id: UUID = Field(..., description="ID of the team")
    team_name: str = Field(..., description="Name of the team")
    total_score: int = Field(..., description="Accumulated score of the team")
    total_penalty: int = Field(
        default=0, description="Total penalty time in seconds (standard for ICPC)"
    )

    model_config = ConfigDict(from_attributes=True)


class LeaderboardResponse(BaseModel):
    """Response containing the complete leaderboard standings for a contest."""

    contest_id: UUID = Field(..., description="ID of the contest")
    result_visibility: ContestResultVisibility = Field(
        default=ContestResultVisibility.HIDDEN,
        description="Result visibility configuration for this contest",
    )
    last_updated_at: datetime = Field(
        ..., description="Timestamp of when the leaderboard was calculated"
    )
    standings: list[LeaderboardRow] = Field(
        ..., description="List of team standings ordered by rank"
    )

    model_config = ConfigDict(from_attributes=True)
