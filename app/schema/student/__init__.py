"""Student-facing schemas for all API endpoints."""

from app.schema.student.contests import (
    StudentContestAvailableResponse,
    StudentContestDetailsResponse,
    StudentContestListResponse,
    StudentContestProblemResponse,
    StudentContestProblemsListResponse,
    StudentContestRegistrationRequest,
    StudentContestRegistrationResponse,
    StudentRegisteredContestListResponse,
    StudentRegisteredContestResponse,
)
from app.schema.student.teams import (
    StudentLeaveTeamResponse,
    StudentTeamAvailableResponse,
    StudentTeamCreateAndJoinResponse,
    StudentTeamCreateRequest,
    StudentTeamJoinRequest,
    StudentTeamJoinResponse,
    StudentTeamListResponse,
    StudentTeamMemberResponse,
    StudentTeamResponse,
)

__all__ = [
    # Contest schemas - Available
    "StudentContestAvailableResponse",
    "StudentContestListResponse",
    # Contest schemas - Registered
    "StudentRegisteredContestResponse",
    "StudentRegisteredContestListResponse",
    # Contest schemas - Details & Problems
    "StudentContestDetailsResponse",
    "StudentContestProblemResponse",
    "StudentContestProblemsListResponse",
    # Contest schemas - Registration
    "StudentContestRegistrationRequest",
    "StudentContestRegistrationResponse",
    # Team schemas
    "StudentTeamResponse",
    "StudentTeamMemberResponse",
    "StudentTeamAvailableResponse",
    "StudentTeamJoinRequest",
    "StudentTeamJoinResponse",
    "StudentTeamCreateRequest",
    "StudentTeamCreateAndJoinResponse",
    "StudentLeaveTeamResponse",
    "StudentTeamListResponse",
]
