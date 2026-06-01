"""Student-facing schemas for all API endpoints."""

from app.schema.student.contest_team_progress import (
    ContestRuntimeDetails,
    ContestSessionStatus,
    ContestTeamProgressResponse,
    PermissionsDetails,
    TeamProgressDetails,
    WorkspaceDetails,
    WorkspaceParticipant,
)
from app.schema.student.contests import (
    ContestSessionStartRequest,
    StudentContestAvailableResponse,
    StudentContestDetailsResponse,
    StudentContestListResponse,
    StudentContestQuestionResponse,
    StudentContestQuestionsListResponse,
    StudentContestRegistrationRequest,
    StudentContestRegistrationResponse,
    StudentQuestionDetailResponse,
    StudentRegisteredContestListResponse,
    StudentRegisteredContestResponse,
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
from app.schema.student.workspace import WorkspaceData, WorkspacePutRequest

__all__ = [
    # Contest schemas - Available
    "StudentContestAvailableResponse",
    "StudentContestListResponse",
    # Contest schemas - Registered
    "StudentRegisteredContestResponse",
    "StudentRegisteredContestListResponse",
    # Contest schemas - Details & Problems
    "StudentContestDetailsResponse",
    "StudentContestQuestionResponse",
    "StudentContestQuestionsListResponse",
    "StudentQuestionDetailResponse",
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
    # Workspace schemas
    "WorkspaceData",
    "WorkspacePutRequest",
]
