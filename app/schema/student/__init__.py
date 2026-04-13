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
    StudentTeamAddMemberRequest,
    StudentTeamAddMemberResponse,
    StudentTeamAvailableResponse,
    StudentTeamCreateAndJoinResponse,
    StudentTeamCreateRequest,
    StudentTeamJoinRequest,
    StudentTeamJoinResponse,
    StudentTeamListResponse,
    StudentTeamMemberResponse,
    StudentTeamRemoveMemberRequest,
    StudentTeamRemoveMemberResponse,
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
    # Team schemas - Member management
    "StudentTeamAddMemberRequest",
    "StudentTeamAddMemberResponse",
    "StudentTeamRemoveMemberRequest",
    "StudentTeamRemoveMemberResponse",
    "StudentLeaveTeamResponse",
    "StudentTeamListResponse",
]
