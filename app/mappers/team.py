from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from app.models.contest import Contest, ContestTeam, ContestTeamProgress
from app.models.team import Team, TeamUser
from app.repositories.dto.team import UNSET, CreateTeamData, UpdateTeamData
from app.schema.team import (
    ContestTeamAnalytics,
    ContestTeamMemberAnalytics,
    ContestTeamMemberDetail,
    ContestTeamMemberQuestionAnalytics,
    ContestTeamMemberQuestionStatistics,
    ContestTeamMemberQuestionSubmissionItem,
    ContestTeamMemberQuestionSubmissions,
    ContestTeamMemberQuestionSubmissionStatistics,
    ContestTeamMemberSubmissionStatistics,
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


def _row_int(row: Any, field: str) -> int:
    return int(getattr(row, field, 0) or 0)


def to_contest_team_analytics(
    team_row: Any,
    member_rows: list[Any],
) -> ContestTeamAnalytics:
    """Map team analytics query rows to the API schema."""
    members = [
        ContestTeamMemberAnalytics(
            id=member.id,
            contest_team_member_id=member.contest_team_member_id,
            name=member.name,
            email=member.email,
            score=_row_int(member, "score"),
            is_flagged=bool(member.is_flagged),
            flagged_reason=member.flagged_reason,
            started_at=member.started_at,
            ended_at=member.ended_at,
            is_participated=bool(member.is_participated),
            is_leader=bool(member.is_leader),
        )
        for member in member_rows
    ]

    return ContestTeamAnalytics(
        contest_team_id=team_row.contest_team_id,
        name=team_row.name,
        score=_row_int(team_row, "score"),
        members=members,
        total_submissions=_row_int(team_row, "total_submissions"),
        accepted_submission=_row_int(team_row, "accepted_submission"),
        wrong_answer=_row_int(team_row, "wrong_answer"),
        time_limit_exceeded=_row_int(team_row, "time_limit_exceeded"),
        runtime_error=_row_int(team_row, "runtime_error"),
        compilation_error=_row_int(team_row, "compilation_error"),
        memory_limit_exceeded=_row_int(team_row, "memory_limit_exceeded"),
        system_error=_row_int(team_row, "system_error"),
        pending_submission=_row_int(team_row, "pending_submission"),
    )


def to_contest_team_member_question_analytics(
    question_rows: list[Any],
) -> list[ContestTeamMemberQuestionAnalytics]:
    """Map contest-team member question analytics rows to response schemas."""
    return [
        ContestTeamMemberQuestionAnalytics(
            question_id=row.question_id,
            title=row.title,
            difficulty=row.difficulty,
            time_limit_ms=row.time_limit_ms,
            memory_limit_mb=row.memory_limit_mb,
            total_submission=_row_int(row, "total_submission"),
            accepted_submission=_row_int(row, "accepted_submission"),
        )
        for row in question_rows
    ]


def to_contest_team_member_detail(
    row: Any,
    *,
    remaining_time_seconds: int,
) -> ContestTeamMemberDetail:
    """Map a contest-team member analytics row to the detail schema."""
    return ContestTeamMemberDetail(
        contest_team_member_id=row.contest_team_member_id,
        user_id=row.user_id,
        name=row.name,
        email=row.email,
        is_leader=bool(row.is_leader),
        is_participated=bool(row.is_participated),
        score=_row_int(row, "score"),
        started_at=row.started_at,
        base_end_time=row.base_end_time,
        ended_at=row.ended_at,
        extra_time_seconds=_row_int(row, "extra_time_seconds"),
        remaining_time_seconds=remaining_time_seconds,
        is_flagged=bool(row.is_flagged),
        flagged_at=row.flagged_at,
        flagged_reason=row.flagged_reason,
        submission_statistics=ContestTeamMemberSubmissionStatistics(
            total=_row_int(row, "total"),
            accepted=_row_int(row, "accepted"),
            wrong_answer=_row_int(row, "wrong_answer"),
            time_limit_exceeded=_row_int(row, "time_limit_exceeded"),
            runtime_error=_row_int(row, "runtime_error"),
            memory_limit_exceeded=_row_int(row, "memory_limit_exceeded"),
            compilation_error=_row_int(row, "compilation_error"),
            system_error=_row_int(row, "system_error"),
            pending=_row_int(row, "pending"),
        ),
        question_statistics=ContestTeamMemberQuestionStatistics(
            attempted=_row_int(row, "attempted"),
            solved=_row_int(row, "solved"),
            unsolved=_row_int(row, "unsolved"),
        ),
    )


def to_contest_team_member_question_submissions(
    question_row: Any,
    statistics_row: Any,
    submission_rows: list[Any],
) -> ContestTeamMemberQuestionSubmissions:
    """Map question submission drilldown rows to the response schema."""
    return ContestTeamMemberQuestionSubmissions(
        question_id=question_row.question_id,
        question_title=question_row.question_title,
        statistics=ContestTeamMemberQuestionSubmissionStatistics(
            total=_row_int(statistics_row, "total"),
            accepted=_row_int(statistics_row, "accepted"),
            wrong_answer=_row_int(statistics_row, "wrong_answer"),
            time_limit_exceeded=_row_int(statistics_row, "time_limit_exceeded"),
            runtime_error=_row_int(statistics_row, "runtime_error"),
            compilation_error=_row_int(statistics_row, "compilation_error"),
        ),
        submissions=[
            ContestTeamMemberQuestionSubmissionItem(
                submission_id=row.submission_id,
                status=row.status,
                score=_row_int(row, "score"),
                language=row.language,
                created_at=row.created_at,
                execution_time=row.execution_time,
                memory=row.memory,
            )
            for row in submission_rows
        ],
    )


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
