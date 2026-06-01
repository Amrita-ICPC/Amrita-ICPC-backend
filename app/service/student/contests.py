from datetime import datetime, timezone
from uuid import UUID

from app.core.cache.decorators import cache_get
from app.core.guards.contest_student import ContestStudentGuard
from app.exceptions.student.contests import (
    ContestSessionNotStartedError,
    NoContestTeamMemberFoundError,
)
from app.mappers.student.contest_mappers import (
    build_contest_session_response,
    build_permissions,
    build_runtime_state,
    build_session_status,
    build_team_progress,
    build_workspace,
    to_student_available_contests_list_response,
    to_student_contest_details_response,
    to_student_contest_not_registered_response,
    to_student_contest_status_response,
    to_team_member_status,
)
from app.models import ContestTeamMemberProgress, ContestTeamProgress
from app.repositories.contest import ContestRepository
from app.repositories.contest_runtime import ContestRuntimeRepository
from app.repositories.contest_team_progress import ContestTeamProgressRepository
from app.repositories.dto.pagination import PaginationParams
from app.repositories.dto.student.contests import StudentContestFilters
from app.repositories.student.contest import StudentContestRepository
from app.repositories.student.contest_team import ContestTeamRepository
from app.repositories.team import TeamRepository
from app.schema.student.contest_team_progress import (
    ContestTeamProgressResponse,
)
from app.schema.student.contests import (
    StudentContestDetailsResponse,
    StudentContestListResponse,
    StudentContestRegistrationRequest,
    StudentContestStatusResponse,
)
from app.utils.contest import (
    calculate_base_end_time,
    calculate_effective_times,
    compute_run_status,
)
from app.utils.enums import (
    ContestRuntimeStatus,
    ContestTeamMemberStatus,
    ContestTeamParticpationType,
    RegistrationState,
    TeamApprovalStatus,
    TeamMemberRole,
    TeamStatus,
)
from app.validators.contest_team import ContestTeamValidator


class StudentContestService:
    """Service class for handling student-facing contest operations.

    This service coordinates repository access, permission guard checks,
    and cache handling for student queries related to contests.
    """

    def __init__(
        self,
        repository: StudentContestRepository,
        contest_repository: ContestRepository,
        contest_team_reposiotry: ContestTeamRepository,
        team_repository: TeamRepository,
        contest_student_guard: ContestStudentGuard,
        contest_team_progress_repository: ContestTeamProgressRepository,
        contest_runtime_repository: ContestRuntimeRepository,
    ) -> None:
        """Initialize the StudentContestService with required dependencies.

        Args:
            repository: Repository for student contest queries.
            contest_repository: Repository for general contest operations.
            team_repository: Repository for team operations.
            contest_student_guard: Guard for student eligibility checks.
        """
        self.repository = repository
        self.contest_student_guard = contest_student_guard
        self.contest_repository = contest_repository
        self.team_repository = team_repository
        self.contest_team_repository = contest_team_reposiotry
        self.contest_team_progress_repository = contest_team_progress_repository
        self.contest_runtime_repository = contest_runtime_repository

    @cache_get(
        key_builder=lambda self, user_id, request, search, pagination: (
            f"student:contests:user:{user_id}:reg:{request.registered}:status:{','.join(request.status) if request.status else 'any'}:search:{search or 'none'}:skip:{pagination.skip}:limit:{pagination.limit}:min_team:{request.min_team_size}:max_team:{request.max_team_size}"
        ),
        ttl=300,
    )
    async def get_all_contests(
        self,
        user_id: UUID,
        request: StudentContestRegistrationRequest,
        search: str | None,
        pagination: PaginationParams,
    ) -> StudentContestListResponse:
        """Retrieve all available contests for a student with filtering and pagination.

        Args:
            user_id: The unique identifier of the requesting user.
            request: Filters such as registration status, run status, and team size bounds.
            search: Optional search keyword for contest names.
            pagination: Pagination parameters including limit and skip values.

        Returns:
            StudentContestListResponse: Paginated list of available contests with total count and teams count.
        """
        filters = StudentContestFilters(
            search_term=search,
            registered=request.registered,
            run_statuses=request.status,
            min_team_size=request.min_team_size,
            max_team_size=request.max_team_size,
        )

        paginated_result, teams_count_dict = await self.repository.get_student_contests(
            user_id=user_id,
            filters=filters,
            pagination=pagination,
        )

        return to_student_available_contests_list_response(
            paginated_result,
            skip=pagination.skip,
            limit=pagination.limit,
            teams_count_dict=teams_count_dict,
            run_status_calculator=compute_run_status,
        )

    @cache_get(
        key_builder=lambda self, contest_id, user_id: (
            f"student:contest:user:{user_id}:contest:{contest_id}"
        ),
        ttl=300,
    )
    async def get_contest_by_id(
        self, contest_id: UUID, user_id: UUID
    ) -> StudentContestDetailsResponse:
        """Retrieve the detailed information of a specific contest for a student.

        Args:
            contest_id: The unique identifier of the contest.
            user_id: The unique identifier of the student making the request.

        Returns:
            StudentContestDetailsResponse: Detailed configuration, run status, and metadata of the contest.

        Raises:
            ContestNotFoundError: If the contest is not found.
            StudentNotEligibleForContestError: If the student does not meet accessibility/audience checks.
        """
        # Get contest details
        contest = await self.contest_repository.get_contest_or_raise(contest_id)

        # Check if the student is eligible for the contest (if the contest is private then check if the student is part of the audience)
        await self.contest_student_guard.check_student_eligibility(
            user_id=user_id, contest=contest
        )
        run_status = compute_run_status(contest.start_time, contest.end_time)

        # Get team count (approved and confirmed teams)
        teams_count = await self.contest_team_repository.count_teams(
            contest_id=contest_id,
            status=TeamStatus.CONFIRMED,
            approval_status=TeamApprovalStatus.APPROVED,
        )

        return to_student_contest_details_response(
            contest=contest,
            run_status=run_status,
            teams_count=teams_count,
        )

    async def get_student_participation_status_in_contest(
        self, contest_id: UUID, user_id: UUID
    ) -> StudentContestStatusResponse:
        """Get the participation status and start readiness of a student in a contest.

        This method calculates the team completion percentage, approved member count,
        individual roles, and checks if the contest is currently open, upcoming, or ended
        relative to the current UTC time.

        Args:
            contest_id: The unique identifier of the contest.
            user_id: The unique identifier of the student.

        Returns:
            StudentContestStatusResponse: Details about registration status, readiness to start, and team composition.

        Raises:
            ContestNotFoundError: If the contest does not exist.
            StudentNotEligibleForContestError: If the student is not eligible to participate in the contest.
        """
        # Check if the student is eligible for the contest
        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        await self.contest_student_guard.check_student_eligibility(
            user_id=user_id, contest=contest
        )

        # Check if the user is in contest_team_member table
        contest_team_member = await self.repository.get_contest_team_member(
            contest_id=contest_id, user_id=user_id
        )

        if not contest_team_member:
            return to_student_contest_not_registered_response()

        contest_team = contest_team_member.contest_team
        contest_team_members = (
            await self.contest_team_repository.get_contest_team_members(
                contest_team_id=contest_team.id,
                contest_team_member_status=[
                    ContestTeamMemberStatus.ACCEPTED,
                    ContestTeamMemberStatus.INVITED,
                ],
            )
        )
        # contest_team_members = contest_team.contest_team_member

        # Calculate status and readiness
        is_draft = contest_team.team_status == TeamStatus.DRAFT
        registered = True
        is_approved = contest_team.approval_status == TeamApprovalStatus.APPROVED
        if is_draft:
            registration_status = RegistrationState.NOT_REGISTERED
        elif contest_team.approval_status == TeamApprovalStatus.WAITING:
            registration_status = RegistrationState.PENDING_APPROVAL
        elif contest_team.approval_status == TeamApprovalStatus.APPROVED:
            registration_status = RegistrationState.APPROVED
        else:
            registration_status = RegistrationState.NOT_REGISTERED

        # Get contest runtime status
        runtime = await self.contest_runtime_repository.get_contest_runtime_by_id(
            contest_id
        )
        contest_runtime_status = (
            runtime.runtime_status if runtime else ContestRuntimeStatus.SCHEDULED
        )

        # Check if already started
        contest_team_progress = (
            await self.contest_team_progress_repository.get_contest_team_progress_by_id(
                contest_id=contest_id,
                contest_team_id=contest_team.id,
            )
        )

        is_individual = (
            contest.participation_type
            == ContestTeamParticpationType.INDIVIDUAL_WORKSPACE
        )
        if is_individual:
            member_progress = await self.contest_team_progress_repository.get_contest_team_member_progress(
                contest_id=contest_id,
                contest_team_id=contest_team.id,
                contest_team_member_id=contest_team_member.id,
            )
            already_started = member_progress is not None
        else:
            already_started = contest_team_progress is not None

        # Determine readiness by evaluating start/end time, runtime status, and leader checks
        current_time = datetime.now(timezone.utc)
        is_leader = contest_team.leader_id == user_id

        if is_draft:
            can_start = False
            reason = "Team is in draft status"
        elif not is_approved:
            can_start = False
            reason = "Team is not approved by contest organizers"
        elif current_time < contest.start_time:
            can_start = False
            reason = "Contest has not started yet"
        elif contest.end_time is not None and current_time > contest.end_time:
            can_start = False
            reason = "Contest has already ended"
        elif contest_runtime_status == ContestRuntimeStatus.SCHEDULED:
            can_start = False
            reason = "Contest has not been started by organizers"
        elif contest_runtime_status == ContestRuntimeStatus.PAUSED:
            can_start = False
            reason = "Contest is currently paused"
        elif contest_runtime_status == ContestRuntimeStatus.FINISHED:
            can_start = False
            reason = "Contest has finished"
        elif contest_runtime_status == ContestRuntimeStatus.CANCELLED:
            can_start = False
            reason = "Contest has been cancelled"
        elif (
            not already_started
            and contest.participation_type
            in (
                ContestTeamParticpationType.SHARED_SINGLE_EDITOR_WORKSPACE,
                ContestTeamParticpationType.LEADER_ONLY,
            )
            and not is_leader
        ):
            can_start = False
            reason = "Only the team leader can start the contest session"
        else:
            can_start = True
            reason = None

        # Calculate member details using pure mapper
        members = [
            to_team_member_status(
                id=member.id,
                user_id=member.user_id,
                name=member.user.name,
                role=TeamMemberRole.LEADER
                if contest_team.leader_id == member.user_id
                else TeamMemberRole.MEMBER,
                joined=member.status == ContestTeamMemberStatus.ACCEPTED,
                confirmed=member.status == ContestTeamMemberStatus.ACCEPTED,
                is_current_user=member.user_id == user_id,
            )
            for member in contest_team_members
        ]

        approved_count = len(
            [
                1
                for member in contest_team_members
                if member.status == ContestTeamMemberStatus.ACCEPTED
            ]
        )
        max_size = contest.max_team_size if contest.max_team_size > 0 else 1
        completion_percentage = (approved_count / max_size) * 100

        # Perform the mapping via decoupled schema mapper
        return to_student_contest_status_response(
            contest_team_id=contest_team.id,
            team_name=contest_team.name,
            members=members,
            approved_count=approved_count,
            min_team_size=contest.min_team_size,
            max_team_size=contest.max_team_size,
            completion_percentage=completion_percentage,
            registered=registered,
            approved=is_approved,
            status_state=registration_status,
            can_start=can_start,
            reason=reason,
            team_approval_status=contest_team.approval_status,
            status=contest_team.team_status,
            team_id=contest_team.team_id,
            contest_runtime_status=contest_runtime_status,
            already_started=already_started,
        )

    # TODO: Handle scheduler exception and add a fallback for scheduler
    async def get_contest_session(
        self, contest_id: UUID, user_id: UUID, is_start: bool = False
    ) -> ContestTeamProgressResponse:
        # Get the contest
        contest = await self.contest_repository.get_contest_or_raise(contest_id)

        # Get the contest_team_member by accepted status and contest ID
        contest_team_member = (
            await self.contest_team_repository.get_contest_team_member_by_user_id(
                user_id=user_id,
                stauts=ContestTeamMemberStatus.ACCEPTED,
                team_status=TeamStatus.CONFIRMED,
                approval_status=TeamApprovalStatus.APPROVED,
                contest_id=contest_id,
            )
        )

        if not contest_team_member:
            raise NoContestTeamMemberFoundError()

        # Check team status and approval
        contest_team = contest_team_member.contest_team
        ContestTeamValidator.validate_student_contest_team(contest_team, contest_id)

        # Get contest runtime
        runtime = await self.contest_runtime_repository.get_contest_runtime_or_raise(
            contest_id
        )
        ContestTeamValidator.validate_student_contest_runtime(runtime)

        # Get team progress record
        contest_team_progress = (
            await self.contest_team_progress_repository.get_contest_team_progress_by_id(
                contest_id=contest_id,
                contest_team_id=contest_team.id,
            )
        )

        member_progress = await self.contest_team_progress_repository.get_contest_team_member_progress(
            contest_id=contest_id,
            contest_team_id=contest_team.id,
            contest_team_member_id=contest_team_member.id,
        )

        is_individual = (
            contest.participation_type
            == ContestTeamParticpationType.INDIVIDUAL_WORKSPACE
        )

        # Check permission constraints based on participation_type
        if (
            is_start
            and contest.participation_type == ContestTeamParticpationType.LEADER_ONLY
        ):
            self.contest_student_guard.check_is_contest_team_leader(
                user_id=user_id, contest_team=contest_team
            )

        # Check start permissions
        if contest_team_progress is None:
            if not is_start:
                raise ContestSessionNotStartedError()

            # For shared workspaces, only the leader can start it
            if (
                contest.participation_type
                == ContestTeamParticpationType.SHARED_SINGLE_EDITOR_WORKSPACE
            ):
                self.contest_student_guard.check_is_contest_team_leader(
                    user_id=user_id, contest_team=contest_team
                )
        else:
            if member_progress is None and not is_start:
                raise ContestSessionNotStartedError()

        now_utc = datetime.now(timezone.utc)
        session_end_time = None
        if contest_team_progress is None or member_progress is None:
            session_end_time = calculate_base_end_time(
                start_time=now_utc,
                end_time=contest.end_time,
                duration=contest.duration,
            )

        already_started = True
        if contest_team_progress is None:
            contest_team_progress = ContestTeamProgress(
                contest_id=contest_id,
                contest_team_id=contest_team.id,
                score=0,
                penalty=0,
                solved_questions_count=0,
                is_flagged=False,
                end_time=None if is_individual else session_end_time,
                extra_time_seconds=0,
                current_editor_user_id=None
                if is_individual
                else contest_team.leader_id,
                created_at=now_utc,
                updated_at=now_utc,
            )
            await self.contest_team_progress_repository.create_contest_team_progress(
                contest_team_progress
            )
            if not is_individual:
                already_started = False

        if member_progress is None:
            member_progress = ContestTeamMemberProgress(
                contest_id=contest_id,
                contest_team_id=contest_team.id,
                contest_team_member_id=contest_team_member.id,
                started_at=now_utc,
                end_time=session_end_time if is_individual else None,
                submissions_count=0,
                accepted_submissions_count=0,
                score=0,
                penalty=0,
                solved_questions_count=0,
                last_activity_at=now_utc,
            )
            await self.contest_team_progress_repository.create_contest_team_member_progress(
                member_progress
            )
            if is_individual:
                already_started = False

        # Calculate effective times
        if is_individual:
            base_end_time = (
                member_progress.end_time if member_progress is not None else None
            )
        else:
            base_end_time = contest_team_progress.end_time

        if base_end_time is None:
            if session_end_time is None:
                session_end_time = calculate_base_end_time(
                    start_time=now_utc,
                    end_time=contest.end_time,
                    duration=contest.duration,
                )
            base_end_time = session_end_time

        effective_end_time, remaining_seconds = calculate_effective_times(
            base_end_time=base_end_time,
            total_paused_duration=runtime.total_paused_duration,
            extra_time_seconds=contest_team_progress.extra_time_seconds,
            is_paused=(runtime.runtime_status == ContestRuntimeStatus.PAUSED),
            paused_at=runtime.paused_at,
        )

        contest_team_members = (
            await self.contest_team_repository.get_contest_team_members(
                contest_team_id=contest_team.id,
                contest_team_member_status=[
                    ContestTeamMemberStatus.ACCEPTED,
                    ContestTeamMemberStatus.INVITED,
                ],
            )
        )

        session_started_at = contest_team_progress.created_at
        if is_individual and member_progress is not None:
            session_started_at = member_progress.started_at

        session_status = build_session_status(
            already_started=already_started,
            started_at=session_started_at,
            ended_at=None,
        )

        runtime_state = build_runtime_state(
            contest_runtime=runtime,
            effective_end_time=effective_end_time,
            remaining_seconds=remaining_seconds,
        )

        assert contest_team.leader_id is not None
        workspace = build_workspace(
            contest_team_members=contest_team_members,
            progress=contest_team_progress,
            user_id=user_id,
            participation_type=contest.participation_type,
            leader_id=contest_team.leader_id,
        )

        team_progress = build_team_progress(
            progress=contest_team_progress,
            member_progress=member_progress,
            is_individual=is_individual,
        )

        permissions = build_permissions(
            is_paused=(runtime.runtime_status == ContestRuntimeStatus.PAUSED),
            remaining_seconds=remaining_seconds,
            progress=contest_team_progress,
            user_id=user_id,
            participation_type=contest.participation_type,
        )

        return build_contest_session_response(
            contest_id=contest_id,
            contest_team_id=contest_team.id,
            session=session_status,
            runtime=runtime_state,
            workspace=workspace,
            team_progress=team_progress,
            permissions=permissions,
        )

    async def start_contest_session(
        self, contest_id: UUID, user_id: UUID
    ) -> ContestTeamProgressResponse:
        return await self.get_contest_session(contest_id, user_id, is_start=True)

    async def get_runtime_session(
        self, contest_id: UUID, user_id: UUID
    ) -> ContestTeamProgressResponse:
        return await self.get_contest_session(contest_id, user_id, is_start=False)
