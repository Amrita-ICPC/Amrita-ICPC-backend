from app.utils.enums import TeamApprovalStatus
from app.repositories.team import TeamRepository
from app.repositories.student.contest import StudentContestRepository
from uuid import UUID
from datetime import datetime, timezone
from app.repositories.contest import ContestRepository
from app.repositories.dto.pagination import PaginationParams
from app.repositories.dto.student.contests import StudentContestFilters
from app.schema.contest import ContestSummaryResponse
from app.schema.student.contests import (
    StudentContestRegistrationRequest, 
    StudentContestListResponse,
    StudentContestDetailsResponse,
    StudentContestStatusResponse,
)
from app.utils.enums import ContestRunStatus, ContestStatus, TeamStatus, TeamMemberRole, ContestTeamMemberStatus
from app.core.cache.decorators import cache_get
from app.mappers.student.contest_mappers import (
    to_student_available_contests_list_response,
    to_student_contest_details_response,
    to_student_contest_status_response,
    to_student_contest_not_registered_response,
    to_team_member_status,
)
from app.utils.contest import compute_run_status
from app.core.guards.contest_student import ContestStudentGuard


class StudentContestService:
    def __init__(self, repository: StudentContestRepository,contest_repository: ContestRepository,team_repository: TeamRepository, contest_student_guard: ContestStudentGuard) -> None:
        self.repository = repository
        self.contest_student_guard = contest_student_guard
        self.contest_repository = contest_repository
        self.team_repository = team_repository

    @cache_get(
        key_builder=lambda self, user_id, request, search, pagination: 
        f"student:contests:user:{user_id}:reg:{request.registered}:status:{','.join(request.status) if request.status else 'any'}:search:{search or 'none'}:skip:{pagination.skip}:limit:{pagination.limit}:min_team:{request.min_team_size}:max_team:{request.max_team_size}",
        ttl=300
    )
    async def get_all_contests(
        self,
        user_id: UUID,
        request: StudentContestRegistrationRequest,
        search: str | None,
        pagination: PaginationParams,
    ) -> StudentContestListResponse:
        """
        Retrieve all available contests for a student with filtering and pagination.
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
            run_status_calculator=compute_run_status
        )

    
    @cache_get(
        key_builder=lambda self, contest_id, user_id: f"student:contest:user:{user_id}:contest:{contest_id}",
        ttl=300
    )
    async def get_contest_by_id(self, contest_id: UUID, user_id: UUID) -> StudentContestDetailsResponse:
        # Get contest details
        contest = await self.contest_repository.get_contest_or_raise(contest_id)

        # Check if the student is eligible for the contest (if the contest is private then check if the student is part of the audience)
        await self.contest_student_guard.check_student_eligibility(user_id=user_id, contest=contest)
        # Get the contest details
        run_status = compute_run_status(contest.start_time, contest.end_time)
        
        #Get team count
        teams_count = await self.team_repository.get_contest_teams_count(contest_id=contest_id)

        return to_student_contest_details_response(
            contest=contest,
            run_status=run_status,
            teams_count=teams_count,
        )

    async def get_student_status_in_contest(
        self, contest_id: UUID, user_id: UUID
    ) -> StudentContestStatusResponse:
        """
        Get the participation status of a student in a contest.
        """
        # Check if the student is eligible for the contest
        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        await self.contest_student_guard.check_student_eligibility(user_id=user_id, contest=contest)
        
        # Check if the user is in contest_team_member table
        contest_team_member = await self.repository.get_contest_team_member(contest_id=contest_id, user_id=user_id)

        if not contest_team_member:
            return to_student_contest_not_registered_response()

        contest_team = contest_team_member.contest_team
        contest_team_members = contest_team.contest_team_member

        # Calculate status and readiness
        is_draft = contest_team.team_status == TeamStatus.DRAFT
        registered = True
        approved = not is_draft
        status_str = "PENDING_APPROVAL" if is_draft else "APPROVED"

        # Determine readiness by evaluating start and end time relative to current time
        current_time = datetime.now(timezone.utc)
        if is_draft:
            can_start = False
            reason = "Team is not approved yet"
        elif current_time < contest.start_time:
            can_start = False
            reason = "Contest has not started yet"
        elif current_time > contest.end_time:
            can_start = False
            reason = "Contest has already ended"
        else:
            can_start = True
            reason = None

        # Calculate member details using pure mapper
        members = [
            to_team_member_status(
                user_id=member.user_id,
                name=member.user.name,
                role=TeamMemberRole.LEADER if contest_team.leader_id == member.user_id else TeamMemberRole.MEMBER,
                joined=member.status != ContestTeamMemberStatus.PENDING,
                confirmed=member.status != ContestTeamMemberStatus.PENDING,
            )
            for member in contest_team_members
        ]

        approved_count = len([1 for member in contest_team_members if member.status == ContestTeamMemberStatus.APPROVED])
        max_size = contest.max_team_size if contest.max_team_size > 0 else 1
        completion_percentage = (approved_count / max_size) * 100

        # Perform the mapping via decoupled schema mapper
        return to_student_contest_status_response(
            contest_team_id=contest_team.id,
            team_name=contest_team.team.name,
            members=members,
            approved_count=approved_count,
            min_team_size=contest.min_team_size,
            max_team_size=contest.max_team_size,
            completion_percentage=completion_percentage,
            registered=registered,
            approved=approved,
            status_str=status_str,
            can_start=can_start,
            reason=reason,
        )        