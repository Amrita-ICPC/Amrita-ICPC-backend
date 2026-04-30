from app.repositories.dto.audience import (
    AudienceRoleCounts,
    AudienceUserBulkData,
    AudienceWithCounts,
    CreateAudienceData,
    UpdateAudienceData,
)
from app.repositories.dto.bank import BankFilters
from app.repositories.dto.contest import (
    ContestFilters,
    ContestQuestionFilters,
    ContestQuestionsPaginatedResult,
    CreateContestData,
    UpdateContestData,
)
from app.repositories.dto.pagination import PaginatedResult, PaginationParams
from app.repositories.dto.student import (
    StudentAvailableContestData,
    StudentAvailableTeamData,
    StudentCodeRunRequestDTO,
    StudentCodeRunResponseDTO,
    StudentContestDetailData,
    StudentContestFilters,
    StudentContestProblemData,
    StudentCreateTeamData,
    StudentRegisteredContestData,
    StudentTeamData,
    StudentTeamFilters,
    StudentTeamJoinData,
    StudentTeamMemberData,
    StudentTeamRegistrationData,
    StudentTestCaseRunResultDTO,
)
from app.repositories.dto.team import CreateTeamData, TeamFilters, UpdateTeamData
from app.repositories.dto.user import UserListFilters

__all__ = [
    "PaginationParams",
    "PaginatedResult",
    "CreateAudienceData",
    "UpdateAudienceData",
    "AudienceUserBulkData",
    "AudienceRoleCounts",
    "AudienceWithCounts",
    "CreateTeamData",
    "UpdateTeamData",
    "TeamFilters",
    "ContestFilters",
    "ContestQuestionFilters",
    "ContestQuestionsPaginatedResult",
    "CreateContestData",
    "UpdateContestData",
    "BankFilters",
    # Student DTOs
    "StudentContestFilters",
    "StudentAvailableContestData",
    "StudentRegisteredContestData",
    "StudentContestDetailData",
    "StudentContestProblemData",
    "StudentCodeRunRequestDTO",
    "StudentCodeRunResponseDTO",
    "StudentTestCaseRunResultDTO",
    "StudentTeamFilters",
    "StudentTeamMemberData",
    "StudentTeamData",
    "StudentAvailableTeamData",
    "StudentTeamRegistrationData",
    "StudentCreateTeamData",
    "StudentTeamJoinData",
    # User DTOs
    "UserListFilters",
]
