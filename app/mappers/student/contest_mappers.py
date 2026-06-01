"""
Mapper functions for student contest operations and responses.

Centralizes all ORM-to-response and request-to-DTO transformations for student contest operations.
Maintains consistency between API schemas and internal data models.

Mapper Organization:
    - Response Mappers: ORM → API Response Schemas
      - to_student_available_contest_response() - Single contest to summary response
      - to_student_available_contests_list_response() - Paginated contest list
      - to_student_registered_contest_response() - Single registered contest
      - to_student_registered_contests_list_response() - Paginated registered list
      - to_student_contest_details_response() - Full contest with problems
      - to_student_contest_problem_response() - Single problem in contest
      - to_student_contest_problems_list_response() - All problems in contest

Key Principles:
    - Pure functions: No side effects, deterministic outputs
    - Type safety: Explicit parameter and return types
    - Documentation: Comprehensive docstrings with use cases
    - Reusability: Share common transformation logic
"""

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from app.models.contest import (
    ContestRuntime,
    ContestTeamMemberProgress,
    ContestTeamProgress,
)
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
    RegistrationStatus,
    StudentContestAvailableResponse,
    StudentContestDetailsResponse,
    StudentContestListResponse,
    StudentContestSessionStatus,
    StudentContestStatusResponse,
    TeamMemberStatus,
    TeamParticipationStatus,
)
from app.utils.enums import ContestRuntimeStatus, WorkspaceMode, WorkspaceRole

if TYPE_CHECKING:
    from app.repositories.dto import PaginatedResult

from app.models.contest import Contest, ContestTeam, ContestTeamMember
from app.models.team import Team
from app.schema.contest import ContestAudienceResponse
from app.utils.enums import (
    ContestRunStatus,
    ContestTeamMemberStatus,
    ContestTeamParticpationType,
    RegistrationState,
    TeamApprovalMode,
    TeamApprovalStatus,
    TeamMemberRole,
    TeamStatus,
)
from app.utils.image import image_object_key_to_url

# Response Mappers: ORM → API Schemas


def to_student_available_contest_response(
    contest: "Contest", *, teams_count: int = 0, run_status: ContestRunStatus
) -> StudentContestAvailableResponse:
    """
    Map Contest ORM object and extra data to student available contest response.
    """
    return StudentContestAvailableResponse(
        id=contest.id,
        name=contest.name,
        description=contest.description,
        image=image_object_key_to_url(contest.image),
        start_time=contest.start_time,
        end_time=contest.end_time,
        registration_start=contest.registration_start,
        registration_end=contest.registration_end,
        status=contest.status,
        run_status=run_status,
        created_at=contest.created_at,
        is_public=contest.is_public,
        team_approval_mode=contest.team_approval_mode,
        contest_mode=contest.contest_mode,
        audiences=[
            ContestAudienceResponse.model_validate(link.audience)
            for link in contest.audience_links
        ]
        if contest.audience_links
        else [],
        max_teams=contest.max_teams,
        min_team_size=contest.min_team_size,
        max_team_size=contest.max_team_size,
        teams_count=teams_count,
        duration=contest.duration,
        show_leaderboard_during_contest=contest.show_leaderboard_during_contest,
        participation_type=contest.participation_type,
    )


def to_student_available_contests_list_response(
    paginated_result: "PaginatedResult",
    skip: int,
    limit: int,
    teams_count_dict: dict[UUID, int],
    run_status_calculator: Callable[[datetime, datetime], ContestRunStatus],
) -> StudentContestListResponse:
    """
    Map paginated Contest results and team counts to paginated list response.
    """
    contests = [
        to_student_available_contest_response(
            contest,
            teams_count=teams_count_dict.get(contest.id, 0),
            run_status=run_status_calculator(contest.start_time, contest.end_time),
        )
        for contest in paginated_result.items
    ]

    total = paginated_result.total
    has_more = (skip + limit) < total
    current_page = (skip // limit) + 1 if limit > 0 else 1

    return StudentContestListResponse(
        contests=contests,
        total=total,
        page=current_page,
        page_size=limit,
        has_more=has_more,
    )


def to_student_contest_details_response(
    contest: "Contest", *, teams_count: int = 0, run_status: ContestRunStatus
) -> StudentContestDetailsResponse:
    """
    Map Contest ORM object and extra data to student contest details response.
    """
    return StudentContestDetailsResponse(
        id=contest.id,
        name=contest.name,
        description=contest.description,
        image=image_object_key_to_url(contest.image),
        start_time=contest.start_time,
        end_time=contest.end_time,
        registration_start=contest.registration_start,
        registration_end=contest.registration_end,
        status=contest.status,
        run_status=run_status,
        created_at=contest.created_at,
        is_public=contest.is_public,
        team_approval_mode=contest.team_approval_mode,
        contest_mode=contest.contest_mode,
        audiences=[
            ContestAudienceResponse.model_validate(link.audience)
            for link in contest.audience_links
        ]
        if contest.audience_links
        else [],
        max_teams=contest.max_teams,
        min_team_size=contest.min_team_size,
        max_team_size=contest.max_team_size,
        teams_count=teams_count,
        rules=contest.rules,
        duration=contest.duration,
        show_leaderboard_during_contest=contest.show_leaderboard_during_contest,
        participation_type=contest.participation_type,
    )


def to_student_contest_not_registered_response() -> StudentContestStatusResponse:
    """
    Map a non-registered status to StudentContestStatusResponse schema.
    """
    return StudentContestStatusResponse(
        registration_status=RegistrationStatus(
            registered=False,
            approved=False,
            status=RegistrationState.NOT_REGISTERED,
        ),
        session=StudentContestSessionStatus(
            can_start=False,
            reason="Not registered for the contest",
            contest_runtime_status=ContestRuntimeStatus.SCHEDULED,
            already_started=False,
        ),
        team=None,
    )


def to_team_member_status(
    id: UUID,
    user_id: UUID,
    name: str,
    role: TeamMemberRole,
    joined: bool,
    confirmed: bool,
    is_current_user: bool,
) -> TeamMemberStatus:
    """
    Map raw team member status data to TeamMemberStatus DTO.
    """
    return TeamMemberStatus(
        id=id,
        user_id=user_id,
        name=name,
        role=role,
        joined=joined,
        confirmed=confirmed,
        is_current_user=is_current_user,
    )


def to_student_contest_status_response(
    contest_team_id: UUID,
    team_name: str,
    members: list[TeamMemberStatus],
    approved_count: int,
    min_team_size: int,
    max_team_size: int,
    completion_percentage: float,
    registered: bool,
    approved: bool,
    status_state: RegistrationState,
    can_start: bool,
    reason: str | None,
    status: TeamStatus,
    team_approval_status: TeamApprovalStatus,
    team_id: UUID | None,
    contest_runtime_status: ContestRuntimeStatus,
    already_started: bool,
) -> StudentContestStatusResponse:
    """
    Map calculated registration, readiness, and team status to StudentContestStatusResponse.
    """
    team_status = TeamParticipationStatus(
        id=contest_team_id,
        name=team_name,
        members=members,
        member_count=approved_count,
        min_team_size=min_team_size,
        max_team_size=max_team_size,
        completion_percentage=completion_percentage,
        team_approval_status=team_approval_status,
        team_status=status,
        team_id=team_id,
    )

    return StudentContestStatusResponse(
        registration_status=RegistrationStatus(
            registered=registered,
            approved=approved,
            status=status_state,
        ),
        session=StudentContestSessionStatus(
            can_start=can_start,
            reason=reason,
            contest_runtime_status=contest_runtime_status,
            already_started=already_started,
        ),
        team=team_status,
    )


def to_contest_team(
    contest_id: UUID,
    team: Team,
    contest: Contest,
) -> ContestTeam:
    """Map a student Team and Contest to a ContestTeam ORM model.

    Args:
        contest_id: UUID of the contest.
        team: Team ORM model instance.
        contest: Contest ORM model instance.

    Returns:
        ContestTeam: The mapped ContestTeam instance.
    """
    return ContestTeam(
        contest_id=contest_id,
        team_id=team.id,
        name=team.name,
        leader_id=team.leader_id,
        team_status=TeamStatus.DRAFT,
        approval_status=(
            TeamApprovalStatus.APPROVED
            if contest.team_approval_mode == TeamApprovalMode.AUTO_APPROVE
            else TeamApprovalStatus.WAITING
        ),
    )


def to_contest_team_members(
    contest_id: UUID,
    contest_team_id: UUID,
    member_ids: list[UUID],
    user_id: UUID,
) -> list[ContestTeamMember]:
    """Map a list of member IDs to ContestTeamMember ORM models.

    Args:
        contest_id: UUID of the associated contest.
        contest_team_id: UUID of the associated contest team.
        member_ids: List of member user IDs.
        user_id: UUID of the requesting/creating user (the team leader).

    Returns:
        list[ContestTeamMember]: List of mapped ContestTeamMember instances.
    """
    return [
        ContestTeamMember(
            contest_id=contest_id,
            contest_team_id=contest_team_id,
            user_id=member_id,
            status=(
                ContestTeamMemberStatus.ACCEPTED
                if member_id == user_id
                else ContestTeamMemberStatus.INVITED
            ),
        )
        for member_id in member_ids
    ]


def build_workspace(
    contest_team_members: list[ContestTeamMember],
    progress: ContestTeamProgress,
    user_id: UUID,
    participation_type: ContestTeamParticpationType,
    leader_id: UUID,
) -> WorkspaceDetails:
    participants = []
    for member in contest_team_members:
        if participation_type == ContestTeamParticpationType.INDIVIDUAL_WORKSPACE:
            role = (
                WorkspaceRole.EDITOR
                if member.user_id == user_id
                else WorkspaceRole.VIEWER
            )
        elif participation_type == ContestTeamParticpationType.LEADER_ONLY:
            role = (
                WorkspaceRole.EDITOR
                if member.user_id == leader_id
                else WorkspaceRole.VIEWER
            )
        else:
            role = (
                WorkspaceRole.EDITOR
                if progress.current_editor_user_id == member.user_id
                else WorkspaceRole.VIEWER
            )
        team_role = (
            TeamMemberRole.LEADER
            if member.user_id == leader_id
            else TeamMemberRole.MEMBER
        )
        is_self = member.user_id == user_id
        participants.append(
            WorkspaceParticipant(
                user_id=member.user_id,
                name=member.user.name,
                avatar_url=None,
                role=role,
                team_role=team_role,
                workspace_role=role,
                is_self=is_self,
                is_online=None,  # TODO: integrate with redis to get online status
            )
        )

    if participation_type == ContestTeamParticpationType.INDIVIDUAL_WORKSPACE:
        mode = WorkspaceMode.INDIVIDUAL
    elif participation_type == ContestTeamParticpationType.LEADER_ONLY:
        mode = WorkspaceMode.LEADER_ONLY
    else:
        mode = WorkspaceMode.SHARED_SINGLE_EDITOR

    return WorkspaceDetails(
        mode=mode,
        current_editor_user_id=progress.current_editor_user_id,
        participants=participants,
    )


def build_runtime_state(
    contest_runtime: ContestRuntime,
    effective_end_time: datetime | None,
    remaining_seconds: int,
) -> ContestRuntimeDetails:
    is_paused = contest_runtime.runtime_status == ContestRuntimeStatus.PAUSED
    paused_at = contest_runtime.paused_at if is_paused else None

    return ContestRuntimeDetails(
        status=contest_runtime.runtime_status,
        effective_end_time=effective_end_time,
        remaining_seconds=remaining_seconds,
        is_paused=is_paused,
        paused_at=paused_at,
        scoreboard_frozen=contest_runtime.scoreboard_frozen,
    )


def build_permissions(
    is_paused: bool,
    remaining_seconds: int,
    progress: ContestTeamProgress,
    user_id: UUID,
    participation_type: ContestTeamParticpationType,
) -> PermissionsDetails:
    is_time_up = remaining_seconds <= 0
    if participation_type == ContestTeamParticpationType.INDIVIDUAL_WORKSPACE:
        can_edit = not is_paused and not is_time_up
        can_submit = not is_paused and not is_time_up
        can_switch_editor = False
    elif participation_type == ContestTeamParticpationType.LEADER_ONLY:
        is_leader = progress.contest_team.leader_id == user_id
        can_edit = not is_paused and not is_time_up and is_leader
        can_submit = not is_paused and not is_time_up and is_leader
        can_switch_editor = False
    else:
        can_edit = (
            not is_paused
            and not is_time_up
            and progress.current_editor_user_id == user_id
        )
        can_submit = not is_paused and not is_time_up
        can_switch_editor = not is_paused and not is_time_up

    return PermissionsDetails(
        can_view=True,
        can_edit=can_edit,
        can_submit=can_submit,
        can_switch_editor=can_switch_editor,
    )


def build_team_progress(
    progress: ContestTeamProgress,
    member_progress: ContestTeamMemberProgress | None = None,
    is_individual: bool = False,
) -> TeamProgressDetails:
    score = (
        member_progress.score
        if is_individual and member_progress is not None
        else progress.score
    )
    penalty = (
        member_progress.penalty
        if is_individual and member_progress is not None
        else progress.penalty
    )
    solved_count = (
        member_progress.solved_questions_count
        if is_individual and member_progress is not None
        else progress.solved_questions_count
    )

    return TeamProgressDetails(
        score=score,
        penalty=penalty,
        solved_count=solved_count,
        last_submission_at=None,
        extra_time_seconds=progress.extra_time_seconds,
        has_extra_time=(progress.extra_time_seconds or 0) > 0,
    )


def build_session_status(
    already_started: bool,
    started_at: datetime | None,
    ended_at: datetime | None = None,
) -> ContestSessionStatus:
    return ContestSessionStatus(
        already_started=already_started,
        started_at=started_at,
        ended_at=ended_at,
    )


def build_contest_session_response(
    contest_id: UUID,
    contest_team_id: UUID,
    session: ContestSessionStatus,
    runtime: ContestRuntimeDetails,
    workspace: WorkspaceDetails,
    team_progress: TeamProgressDetails,
    permissions: PermissionsDetails,
) -> ContestTeamProgressResponse:
    return ContestTeamProgressResponse(
        contest_id=contest_id,
        contest_team_id=contest_team_id,
        session=session,
        runtime=runtime,
        workspace=workspace,
        team_progress=team_progress,
        permissions=permissions,
    )
