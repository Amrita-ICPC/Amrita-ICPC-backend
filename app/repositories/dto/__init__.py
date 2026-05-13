from app.repositories.dto.audience import (
    AudienceRoleCounts,
    AudienceUserBulkData,
    AudienceWithCounts,
    CreateAudienceData,
    UpdateAudienceData,
)
from app.repositories.dto.bank import BankFilters, BankQuestionFilters
from app.repositories.dto.contest import (
    UNSET,
    ContestFilters,
    ContestQuestionFilters,
    ContestQuestionsPaginatedResult,
    CreateContestData,
    UpdateContestData,
)
from app.repositories.dto.pagination import PaginatedResult, PaginationParams

from app.repositories.dto.question import (
    CreateQuestionData,
    CreateQuestionTemplateData,
    CreateQuestionTestCaseData,
    UpdateQuestionData,
)
from app.repositories.dto.team import CreateTeamData, TeamFilters, UpdateTeamData
from app.repositories.dto.user import UserListFilters
from app.repositories.dto.student import (
    StudentAvailableTeamData,
    StudentCodeRunRequestDTO,
    StudentCodeRunResponseDTO,
    StudentContestFilters,
    StudentCreateTeamData,
    StudentTeamData,
    StudentTeamFilters,
    StudentTeamJoinData,
    StudentTeamMemberData,
    StudentTeamRegistrationData,
    StudentTestCaseRunResultDTO,
)

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
    "BankQuestionFilters",
    # Question DTOs
    "CreateQuestionData",
    "CreateQuestionTemplateData",
    "CreateQuestionTestCaseData",
    "UpdateQuestionData",
    # Student DTOs
    "StudentContestFilters",
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
    "UNSET",
]
