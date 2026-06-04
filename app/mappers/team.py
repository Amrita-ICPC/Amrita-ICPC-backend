from typing import TYPE_CHECKING, cast
from uuid import UUID

from app.models.contest import Contest, ContestTeam, ContestTeamProgress
from app.models.team import Team, TeamUser
from app.repositories.dto.team import UNSET, CreateTeamData, UpdateTeamData
from app.schema.team import (
    ContestTeamResponse,
    TeamCreate,
    TeamListResponse,
    TeamMemberResponse,
    TeamUpdate,
)
from app.utils.enums import TeamApprovalMode, TeamApprovalStatus, UserRole

if TYPE_CHECKING:
    from app.models.contest import ContestTeam, ContestTeamMember
    from app.models.team import Team
    from app.models.user import User


def build_create_team_dto(
    contest_id: UUID,
    team_data: TeamCreate,
    created_by: UUID,
) -> CreateTeamData:
    """Map team create schema to repository create DTO."""
    return CreateTeamData(
        contest_id=contest_id,
        created_by=created_by,
        name=team_data.name,
        description=team_data.description,
        logo=team_data.logo,
        leader_id=team_data.leader_id,
        member_ids=team_data.member_ids,
        status=team_data.status,
    )


def build_update_team_dto(team_id: UUID, team_data: TeamUpdate) -> UpdateTeamData:
    """Map team update schema to repository update DTO."""
    fields_set = team_data.model_fields_set
    return UpdateTeamData(
        team_id=team_id,
        name=team_data.name,
        description=team_data.description if "description" in fields_set else UNSET,
        logo=team_data.logo if "logo" in fields_set else UNSET,
        status=team_data.status,
        leader_id=team_data.leader_id if "leader_id" in fields_set else UNSET,
    )


def build_leader_update_dto(
    team_id: UUID, leader_id: UUID | None, *, leader_id_set: bool
) -> UpdateTeamData:
    """Build minimal DTO for leader-only updates."""
    return UpdateTeamData(
        team_id=team_id,
        leader_id=leader_id if leader_id_set else UNSET,
    )


def to_contest_team_response(
    contest_team: "ContestTeam",
    members: list["ContestTeamMember"] | None = None,
) -> ContestTeamResponse:
    """Map contest team ORM object to response schema."""
    if members is not None:
        return ContestTeamResponse.from_contest_team(contest_team, members=members)
    return ContestTeamResponse.from_contest_team(contest_team)


def to_contest_team_response_list(
    contest_teams: list["ContestTeam"],
) -> list[ContestTeamResponse]:
    """Map contest team ORM list to response schema list."""
    return [to_contest_team_response(contest_team) for contest_team in contest_teams]


def to_team_list_response(
    total: int,
    contest_teams: list["ContestTeam"],
    status_counts: dict[str, int],
    team_members_map: dict[UUID, list["ContestTeamMember"]] | None = None,
) -> TeamListResponse:
    """Map contest team list and counts to TeamListResponse."""
    teams_responses: list[ContestTeamResponse] = []
    for team in contest_teams:
        members = team_members_map.get(team.id) if team_members_map else None
        teams_responses.append(to_contest_team_response(team, members))
    return TeamListResponse(
        total=total,
        teams=teams_responses,
        approved_count=status_counts.get("approved_count", 0),
        waiting_count=status_counts.get("waiting_count", 0),
        rejected_count=status_counts.get("rejected_count", 0),
        disqualified_count=status_counts.get("disqualified_count", 0),
    )


def to_team_member_responses(
    users: list["User"],
    *,
    team: "Team",
) -> list[TeamMemberResponse]:
    """Map user ORM list to team member responses."""
    return [
        TeamMemberResponse(
            id=user.id,
            user_id=user.user_id,
            name=user.name,
            email=user.email,
            role=user.role.value,
            is_leader=(team.leader_id == user.id),
        )
        for user in users
    ]


def to_contest_team_member_responses(
    contest_team_members: list["ContestTeamMember"],
    *,
    leader_id: UUID | None,
) -> list[TeamMemberResponse]:
    """Map ContestTeamMember list to team member responses."""
    return [
        TeamMemberResponse(
            id=ctm.user.id,
            user_id=ctm.user.user_id,
            name=ctm.user.name,
            email=ctm.user.email,
            role=ctm.user.role.value,
            is_leader=(leader_id == ctm.user.id),
        )
        for ctm in contest_team_members
    ]


def build_team_creation_entities(
    team_data: CreateTeamData,
    *,
    contest: Contest,
    creator_role: UserRole,
) -> tuple[Team, ContestTeam, ContestTeamProgress, list[TeamUser]]:
    """Build team creation ORM entities from repository DTO and context."""
    team = Team(
        name=team_data.name,
        description=team_data.description,
        logo=team_data.logo,
        leader_id=team_data.leader_id,
        created_by=team_data.created_by,
    )

    approval_status = TeamApprovalStatus.APPROVED
    if (
        contest.team_approval_mode == TeamApprovalMode.INSTRUCTOR_REVIEW
        and creator_role != UserRole.instructor
    ):
        approval_status = TeamApprovalStatus.WAITING

    contest_team = ContestTeam(
        contest_id=team_data.contest_id,
        team=team,
        team_status=team_data.status,
        approval_status=approval_status,
    )

    progress = ContestTeamProgress(contest_id=team_data.contest_id)
    contest_team.progress = [progress]

    team_users = [
        TeamUser(team=team, user_id=member_id) for member_id in team_data.member_ids
    ]
    return team, contest_team, progress, team_users


def apply_team_updates(
    *,
    team_data: UpdateTeamData,
    team: Team,
    contest_team: ContestTeam,
) -> None:
    """Apply team update DTO values onto team and contest-team ORM entities."""
    if team_data.name is not None and team_data.name != team.name:
        team.name = team_data.name
    if team_data.description is not UNSET and team_data.description != team.description:
        team.description = cast(str | None, team_data.description)
    if team_data.logo is not UNSET and team_data.logo != team.logo:
        team.logo = cast(str | None, team_data.logo)
    if team_data.status is not None and team_data.status != contest_team.team_status:
        contest_team.team_status = team_data.status
    if team_data.leader_id is not UNSET and team_data.leader_id != team.leader_id:
        team.leader_id = cast(UUID | None, team_data.leader_id)
