from dataclasses import dataclass
from uuid import UUID

from app.utils.enums import TeamApprovalStatus, TeamStatus


class _UnsetType:
    """Sentinel type for omitted patch fields."""


UNSET = _UnsetType()


@dataclass
class CreateTeamData:
    """
    Data transfer object for creating teams in the repository layer.

    This class encapsulates the data needed to create a team without exposing
    the API schema (TeamCreate DTO) to the repository layer, maintaining
    separation of concerns.
    """

    contest_id: UUID
    name: str
    description: str | None
    logo: str | None
    leader_id: UUID | None
    member_ids: list[UUID]
    status: TeamStatus
    created_by: UUID


@dataclass
class UpdateTeamData:
    """
    Data transfer object for updating teams in the repository layer.

    This class encapsulates the data needed to update a team without exposing
    the API schema (TeamUpdate DTO) to the repository layer, maintaining
    separation of concerns.
    """

    team_id: UUID
    name: str | None = None
    description: str | None | _UnsetType = UNSET
    logo: str | None | _UnsetType = UNSET
    status: TeamStatus | None = None
    leader_id: UUID | None | _UnsetType = UNSET


@dataclass
class TeamFilters:
    search_term: str | None = None
    status: list[TeamStatus] | None = None
    approval_status: TeamApprovalStatus | None = None
