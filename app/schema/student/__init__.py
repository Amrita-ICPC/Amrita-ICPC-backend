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
    ContestSessionStartRequest,
)
from app.schema.student.run import (
    StudentCodeRunRequest,
    StudentCodeRunResponse,
    StudentTestCaseRunResultResponse,
)
from app.schema.student.teams import (
    StudentTeamCardResponse,
    StudentTeamCreateRequest,
    StudentTeamInvitationListResponse,
    StudentTeamInvitationResponse,
    StudentTeamInvitationUpdateRequest,
    StudentTeamListResponse,
    StudentTeamMemberSummaryResponse,
    StudentTeamsResponse,
    StudentTeamTransferLeaderRequest,
    StudentTeamUpdateRequest,
    TeamMemberDetailResponse,
)
from app.schema.student.contest_team_progress import (
    ContestSessionStatus,
    ContestRuntimeDetails,
    WorkspaceParticipant,
    WorkspaceDetails,
    TeamProgressDetails,
    PermissionsDetails,
    ContestTeamProgressResponse,
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
    "ContestSessionStartRequest",
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
    # Contest Team Progress schemas
    "ContestSessionStatus",
    "ContestRuntimeDetails",
    "WorkspaceParticipant",
    "WorkspaceDetails",
    "TeamProgressDetails",
    "PermissionsDetails",
    "ContestTeamProgressResponse",
]

