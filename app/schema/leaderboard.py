from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LeaderboardQuestionDetail(BaseModel):
    """Details of a team's submission status for a single contest question."""

    question_id: UUID = Field(..., description="ID of the question")
    question_title: str = Field(..., description="Title of the question")
    is_solved: bool = Field(
        ..., description="Whether the team has solved this question (AC)"
    )
    score: int = Field(default=0, description="Score achieved on this question")
    attempts: int = Field(default=0, description="Total number of evaluation attempts")
    time_taken_seconds: int | None = Field(
        None,
        description="Time taken in seconds from contest start to solve the question",
    )

    model_config = ConfigDict(from_attributes=True)


class LeaderboardRow(BaseModel):
    """A single row/entry in the contest leaderboard representing a team's standing."""

    rank: int = Field(..., description="Current rank of the team")
    team_id: UUID = Field(..., description="ID of the team")
    team_name: str = Field(..., description="Name of the team")
    total_score: int = Field(..., description="Accumulated score of the team")
    total_penalty: int = Field(
        default=0, description="Total penalty time in seconds (standard for ICPC)"
    )
    question_details: list[LeaderboardQuestionDetail] = Field(
        default_factory=list,
        description="Performance details for each question in the contest",
    )

    model_config = ConfigDict(from_attributes=True)


class LeaderboardResponse(BaseModel):
    """Response containing the complete leaderboard standings for a contest."""

    contest_id: UUID = Field(..., description="ID of the contest")
    last_updated_at: datetime = Field(
        ..., description="Timestamp of when the leaderboard was calculated"
    )
    standings: list[LeaderboardRow] = Field(
        ..., description="List of team standings ordered by rank"
    )

    model_config = ConfigDict(from_attributes=True)
