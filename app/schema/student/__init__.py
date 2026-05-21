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
from app.schema.student.run import (
    StudentCodeRunRequest,
    StudentCodeRunResponse,
    StudentTestCaseRunResultResponse,
)
from app.schema.student.teams import (
    StudentTeamMemberSummaryResponse,
    StudentTeamCardResponse,
    StudentTeamListResponse,
    StudentTeamsResponse,
    StudentTeamCreateRequest,
    StudentTeamUpdateRequest,
    StudentTeamInvitationResponse,
    StudentTeamInvitationListResponse,
    StudentTeamInvitationUpdateRequest,
    StudentTeamTransferLeaderRequest,
    TeamMemberDetailResponse,
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
    # Run schemas - Code execution
    "StudentCodeRunRequest",
    "StudentCodeRunResponse",
    "StudentTestCaseRunResultResponse",
    # Team schemas
    "StudentTeamMemberSummaryResponse",
    "StudentTeamCardResponse",
    "StudentTeamListResponse",
    "StudentTeamsResponse",
    "StudentTeamCreateRequest",
    "StudentTeamUpdateRequest",
    "StudentTeamInvitationResponse",
    "StudentTeamInvitationListResponse",
    "StudentTeamInvitationUpdateRequest",
    "StudentTeamTransferLeaderRequest",
    "TeamMemberDetailResponse",
]

