from datetime import datetime, timezone
from uuid import UUID

from app.core.cache import keys as cache_keys
from app.core.cache.decorators import cache_delete
from app.core.guards.contest_student import ContestStudentGuard
from app.core.guards.team_student import TeamStudentGuard
from app.exceptions.contest import (
    ContestResultsNotVisibleError,
    ContestTeamNotFoundException,
    StudentAlreadyInContestError,
    StudentContestSessionAlreadyStartedError,
)
from app.exceptions.student.teams import (
    TeamStatusNotAllowedForUpdatingContestTeamMemberStatusException,
)
from app.exceptions.team import (
    CannotRemoveTeamLeaderError,
    InvalidTeamSizeError,
    MemberAlreadyInTeamError,
    TeamMemberAccessDeniedError,
    TeamNotHavingRequiredNumberOfMembersException,
)
from app.mappers.student.analytics import (
    to_student_member_detail,
    to_student_member_question_analytics,
    to_student_member_question_submissions,
    to_student_team_analytics,
)
from app.mappers.student.contest_mappers import to_contest_team, to_contest_team_members
from app.models import Contest, ContestTeam, ContestTeamMember
from app.repositories.contest import ContestRepository
from app.repositories.student.contest_team import ContestTeamRepository
from app.repositories.student.team import StudentTeamRepository
from app.repositories.team import TeamRepository
from app.schema.leaderboard import LeaderboardResponse
from app.schema.student.analytics import (
    StudentMemberDetail,
    StudentMemberQuestionAnalytics,
    StudentMemberQuestionSubmissions,
    StudentTeamAnalytics,
)
from app.schema.student.contest_team import ContestTeamUpdate
from app.schema.team import ContestTeamCreate, ContestTeamImport
from app.service.contest_service import ContestService
from app.utils.enums import (
    ContestMode,
    ContestTeamMemberStatus,
    ContestTeamParticipationType,
    TeamApprovalMode,
    TeamApprovalStatus,
    TeamStatus,
)
from app.validators.contest import ContestValidator
from app.validators.contest_team import ContestTeamValidator
from app.validators.team import TeamValidator


class ContestTeamService:
    """Service class for managing contest teams (student-facing operations)."""

    def __init__(
        self,
        repository: ContestTeamRepository,
        team_repository: StudentTeamRepository,
        team_student_guard: TeamStudentGuard,
        contest_repository: ContestRepository,
        contest_student_guard: ContestStudentGuard,
        team_analytics_repository: TeamRepository | None = None,
    ) -> None:
        """Initialize the ContestTeamService with required dependencies.

        Args:
            repository: Repository for contest team database operations.
            team_repository: Repository for student teams.
            team_student_guard: Guard for validating student team permissions.
            contest_repository: Repository for contests.
            contest_student_guard: Guard for validating student contest access.
            team_analytics_repository: Repository providing team analytics queries.
        """
        self.repository = repository
        self.team_repository = team_repository
        self.team_student_guard = team_student_guard
        self.contest_repository = contest_repository
        self.contest_student_guard = contest_student_guard
        self.team_analytics_repository = team_analytics_repository

    async def _ensure_students_have_not_started_session(
        self, contest_id: UUID, user_ids: list[UUID]
    ) -> None:
        for user_id in user_ids:
            if await self.repository.has_started_contest_session(contest_id, user_id):
                raise StudentContestSessionAlreadyStartedError(
                    str(user_id), str(contest_id)
                )

    @cache_delete(
        key_builder=lambda self, contest_id, contest_team_import, user_id: (
            cache_keys.student_contests_bust()
        )
    )
    async def import_team(
        self,
        contest_id: UUID,
        contest_team_import: ContestTeamImport,
        user_id: UUID,
    ) -> None:
        """Import an existing student team and its members into a contest.

        Args:
            contest_id: UUID of the contest.
            contest_team_import: DTO containing team_id and member_ids.
            user_id: UUID of the student requesting the import.
        """
        # Fetch the team and contest
        contest = await self.contest_repository.get_contest_or_raise(contest_id)

        TeamValidator.validate_team_operations_allowed(
            contest.contest_mode, "import team"
        )

        ContestValidator.validate_registration_date_past(
            contest.registration_start, contest.registration_end
        )

        team = await self.team_repository.get_student_team_by_id_or_raise(
            user_id, contest_team_import.team_id
        )

        # Check if the user is leader
        self.team_student_guard.check_is_leader(team=team, user_id=user_id)

        existing_members_ids = set([team_user.user_id for team_user in team.members])

        TeamValidator.validate_members_in_team(
            team_name=team.name,
            existing_member_ids=existing_members_ids,
            member_ids_to_check=set(contest_team_import.member_ids),
        )

        if team.leader_id is not None:
            TeamValidator.validate_leader_in_members(
                leader_id=team.leader_id,
                member_ids=set(contest_team_import.member_ids),
                team_name=team.name,
            )

        # Check if the team is already in the contest
        await self.contest_student_guard.check_team_already_in_contest(
            team_id=team.id, contest_id=contest_id
        )

        # Check if the student is already in the contest
        await self.contest_student_guard.check_student_already_in_contest(
            contest_id=contest_id, user_ids=contest_team_import.member_ids
        )
        await self._ensure_students_have_not_started_session(
            contest_id=contest_id,
            user_ids=contest_team_import.member_ids,
        )

        # Check the audiences of the members
        if not contest.is_public:
            await self.contest_student_guard.check_student_audiences_for_contest(
                user_ids=contest_team_import.member_ids,
                contest_id=contest_id,
            )

        # Validate max teams limit. Locked so two concurrent imports/creates
        # into this contest can't both pass the count check before either
        # insert commits (see acquire_team_count_lock docstring).
        if (
            contest.max_teams is not None
            and isinstance(contest.max_teams, int)
            and contest.max_teams > 0
        ):
            await self.repository.acquire_team_count_lock(contest_id)
            counts = await self.repository.count_teams_by_status(contest_id)
            ContestTeamValidator.validate_max_teams(
                approved_teams_count=counts["approved_count"],
                max_teams=contest.max_teams,
                contest_id=contest_id,
            )

        # Map and create ContestTeam
        contest_team = to_contest_team(
            contest_id=contest_id,
            team=team,
            contest=contest,
        )
        contest_team = await self.repository.create_contest_team(contest_team)

        # Map and create ContestTeamMembers
        contest_team_members = to_contest_team_members(
            contest_id=contest_id,
            contest_team_id=contest_team.id,
            member_ids=contest_team_import.member_ids,
            user_id=user_id,
        )
        await self.repository.create_contest_team_members(contest_team_members)

        return None

    @cache_delete(
        key_builder=lambda self, contest_id, contest_team_create, user_id: (
            cache_keys.student_contests_bust()
        )
    )
    async def create_contest_team(
        self,
        contest_id: UUID,
        contest_team_create: ContestTeamCreate,
        user_id: UUID,
    ) -> None:
        """Create a new contest team directly in a contest (not in standard teams).

        Args:
            contest_id: UUID of the contest.
            contest_team_create: Schema containing team name.
            user_id: UUID of the user creating the team.
        """
        # Fetch contest
        contest = await self.contest_repository.get_contest_or_raise(contest_id)

        # Validate registration timeframe
        ContestValidator.validate_registration_date_past(
            contest.registration_start, contest.registration_end
        )

        # Check if user is already in the contest
        await self.contest_student_guard.check_student_already_in_contest(
            contest_id=contest_id,
            user_ids=[user_id],
        )
        await self._ensure_students_have_not_started_session(
            contest_id=contest_id,
            user_ids=[user_id],
        )

        # Check user's audience eligibility for the contest
        if not contest.is_public:
            await self.contest_student_guard.check_student_audiences_for_contest(
                user_ids=[user_id],
                contest_id=contest_id,
            )

        # Validate max teams limit. Locked so two concurrent imports/creates
        # into this contest can't both pass the count check before either
        # insert commits (see acquire_team_count_lock docstring).
        if (
            contest.max_teams is not None
            and isinstance(contest.max_teams, int)
            and contest.max_teams > 0
        ):
            await self.repository.acquire_team_count_lock(contest_id)
            counts = await self.repository.count_teams_by_status(contest_id)
            ContestTeamValidator.validate_max_teams(
                approved_teams_count=counts["approved_count"],
                max_teams=contest.max_teams,
                contest_id=contest_id,
            )

        # Create the ContestTeam association
        # Keep team_id=None (as it's not a standard team)
        # Set team_status=DRAFT (default)
        # Set leader_id=user_id
        team_status = TeamStatus.DRAFT
        approval_status = TeamApprovalStatus.APPROVED

        if contest.contest_mode == ContestMode.INDIVIDUAL:
            team_status = TeamStatus.CONFIRMED
            if contest.team_approval_mode == TeamApprovalMode.AUTO_APPROVE:
                approval_status = TeamApprovalStatus.APPROVED
            else:
                approval_status = TeamApprovalStatus.WAITING

        contest_team = ContestTeam(
            contest_id=contest_id,
            name=contest_team_create.name,
            leader_id=user_id,
            team_status=team_status,
            approval_status=approval_status,
            team_id=None,
        )
        contest_team = await self.repository.create_contest_team(contest_team)

        # Add the leader to the ContestTeamMember table
        # When creating a team, the leader is automatically accepted
        contest_team_member = ContestTeamMember(
            contest_id=contest_id,
            contest_team_id=contest_team.id,
            user_id=user_id,
            status=ContestTeamMemberStatus.ACCEPTED,
            confirmed_at=datetime.now(timezone.utc),
        )
        await self.repository.create_contest_team_members([contest_team_member])

        return None

    async def update_contest_team(
        self,
        contest_team_id: UUID,
        contest_team_update: ContestTeamUpdate,
        user_id: UUID,
    ) -> None:
        # Fetch the contest team
        contest_team = await self.repository.get_contest_team_by_id_or_raise(
            contest_team_id
        )

        # Renaming is a roster-adjacent mutation like invite/accept, so it's
        # bound by the same registration window (see invite_members/
        # create_contest_team for the equivalent check elsewhere in this file).
        contest = await self.contest_repository.get_contest_or_raise(
            contest_team.contest_id
        )
        ContestValidator.validate_registration_date_past(
            contest.registration_start, contest.registration_end
        )

        TeamValidator.validate_team_confirmation(
            contest_team.team_status, contest_team.name
        )

        ContestTeamValidator.validate_team_status(contest_team.team_status)

        # Check if the user is leader
        self.team_student_guard.check_is_contest_team_leader(
            contest_team=contest_team, user_id=user_id
        )

        # update the name
        contest_team.name = contest_team_update.name

        await self.repository.update_contest_team(contest_team)

        return None

    async def transfer_team_leader(
        self,
        contest_team_id: UUID,
        new_leader_id: UUID,
        user_id: UUID,
    ) -> None:
        # Fetch the contest team
        contest_team = await self.repository.get_contest_team_by_id_or_raise(
            contest_team_id
        )

        # Leadership transfer is a roster-adjacent mutation like invite/accept,
        # so it's bound by the same registration window (see invite_members/
        # create_contest_team for the equivalent check elsewhere in this file).
        contest = await self.contest_repository.get_contest_or_raise(
            contest_team.contest_id
        )
        ContestValidator.validate_registration_date_past(
            contest.registration_start, contest.registration_end
        )

        TeamValidator.validate_team_confirmation(
            contest_team.team_status, contest_team.name
        )

        ContestTeamValidator.validate_team_status(contest_team.team_status)

        # Check if the user is leader
        self.team_student_guard.check_is_contest_team_leader(
            contest_team=contest_team, user_id=user_id
        )

        # Check if the new leader is a member of the team
        if contest_team.team_id is not None:
            await self.team_student_guard.check_is_member(
                team_id=contest_team.team_id, user_id=new_leader_id
            )

        # check if the new leader is a member of the contest team
        await self.contest_student_guard.check_contest_team_member_exist(
            contest_team_id=contest_team_id, user_id=new_leader_id
        )

        # Transfer the team leader
        contest_team.leader_id = new_leader_id

        await self.repository.update_contest_team(contest_team)

        return None

    @cache_delete(
        key_builder=lambda self, contest_id, contest_team_id, user_id, contest_team_status: [
            *cache_keys.student_contests_bust(),
            cache_keys.student_session_validation_bust_pattern(contest_id),
        ]
    )
    async def update_contest_team_status(
        self,
        contest_id: UUID,
        contest_team_id: UUID,
        user_id: UUID,
        contest_team_status: TeamStatus,
    ) -> None:
        """Update the status of a contest team."""

        # Fetch the contest team
        contest_team = await self.repository.get_contest_team_by_id_or_raise(
            contest_team_id
        )

        # A contest_team_id is only meaningful within its own contest; without
        # this check a leader could confirm their team using another contest's
        # min/max team size and approval mode by passing a mismatched contest_id.
        if contest_team.contest_id != contest_id:
            raise ContestTeamNotFoundException(str(contest_team_id))

        ContestTeamValidator.validate_team_status(contest_team.team_status)

        TeamValidator.validate_allowed_student_team_status(contest_team.team_status)

        # Check if the user is leader
        self.team_student_guard.check_is_contest_team_leader(
            contest_team=contest_team, user_id=user_id
        )

        # Status(Confirmed) check the required thisngs before the update
        if contest_team_status == TeamStatus.CONFIRMED:
            contest = await self.contest_repository.get_contest_or_raise(contest_id)
            # Confirming is a roster-lifecycle action like invite/accept, so
            # it's bound by the same registration window (unlike CANCELLED
            # below, which stays intentionally exempt to allow cleanup after
            # registration closes).
            ContestValidator.validate_registration_date_past(
                contest.registration_start, contest.registration_end
            )
            # Count only ACCEPTED members: REJECTED/LEFT/REMOVED members aren't
            # actually on the team, and INVITED members can no longer accept once
            # the team is CONFIRMED (accepting requires team_status == DRAFT), so
            # counting them would let a team confirm with invitees who can never
            # join.
            team_member_count = await self.repository.count_contest_team_members(
                contest_team_id, ContestTeamMemberStatus.ACCEPTED
            )
            if contest.min_team_size <= team_member_count <= contest.max_team_size:
                contest_team.team_status = contest_team_status
                if contest.team_approval_mode == TeamApprovalMode.AUTO_APPROVE:
                    contest_team.approval_status = TeamApprovalStatus.APPROVED
            else:
                raise TeamNotHavingRequiredNumberOfMembersException(
                    team_name=contest_team.name,
                    team_member_count=team_member_count,
                    min_team_size=contest.min_team_size,
                    max_team_size=contest.max_team_size,
                )
        elif contest_team_status == TeamStatus.CANCELLED:
            await self._cancel_contest_team(contest_team)
            return None
        else:
            # Only CONFIRMED and CANCELLED are allowed student-initiated status changes
            raise ValueError(f"Invalid team status transition: {contest_team_status}")

        await self.repository.update_contest_team(contest_team)

        return None

    @cache_delete(
        key_builder=lambda self, user_id, contest_id, contest_team_id, contest_team_member_id, contest_team_member_status: [
            *cache_keys.student_contests_bust(),
            cache_keys.student_session_validation_bust_pattern(contest_id),
        ]
    )
    async def update_contest_team_member_status(
        self,
        user_id: UUID,
        contest_id: UUID,
        contest_team_id: UUID,
        contest_team_member_id: UUID,
        contest_team_member_status: ContestTeamMemberStatus,
    ) -> None:
        """Update the status of a contest team member."""
        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        contest_team = await self.repository.get_contest_team_by_id_or_raise(
            contest_team_id
        )
        contest_team_member = await self.repository.get_contest_team_member_or_raise(
            contest_team_member_id
        )

        # Validate Contest Lifecycle
        ContestTeamValidator.validate_contest_team_member_life_cycle(
            contest_team_member.status, contest_team_member_status
        )

        # Validate dates and team status (if not CANCELLED)
        if contest_team_member_status != ContestTeamMemberStatus.CANCELLED:
            ContestValidator.validate_registration_date_past(
                contest.registration_start, contest.registration_end
            )
            if contest_team.team_status != TeamStatus.DRAFT:
                raise TeamStatusNotAllowedForUpdatingContestTeamMemberStatusException()

        # Handle status transitions
        if contest_team_member_status == ContestTeamMemberStatus.REMOVED:
            await self._handle_member_removed(
                user_id, contest_team, contest_team_member
            )
        elif contest_team_member_status == ContestTeamMemberStatus.LEFT:
            await self._handle_member_left(
                user_id, contest_team_id, contest_team, contest_team_member
            )
        elif contest_team_member_status == ContestTeamMemberStatus.ACCEPTED:
            await self._handle_member_accepted(
                user_id, contest_team_id, contest_team, contest_team_member, contest
            )
        elif contest_team_member_status == ContestTeamMemberStatus.REJECTED:
            # A user can only reject their own invitation
            if contest_team_member.user_id != user_id:
                raise TeamMemberAccessDeniedError(
                    team_id=str(contest_team.id), user_id=str(user_id)
                )
        elif contest_team_member_status == ContestTeamMemberStatus.CANCELLED:
            # The leader or the system cancels it
            self.team_student_guard.check_is_contest_team_leader(
                contest_team=contest_team, user_id=user_id
            )
            if contest_team_member.user_id == contest_team.leader_id:
                await self._cancel_contest_team(
                    contest_team, exclude_user_id=contest_team_member.user_id
                )

        # Common status update and database save
        contest_team_member.status = contest_team_member_status
        if contest_team_member_status == ContestTeamMemberStatus.ACCEPTED:
            contest_team_member.confirmed_at = datetime.now(timezone.utc)
        await self.repository.update_contest_team_member(contest_team_member)

        return None

    async def _cancel_contest_team(
        self, contest_team: ContestTeam, exclude_user_id: UUID | None = None
    ) -> None:
        """Helper to cancel a contest team and all its invited/accepted members."""
        await self.repository.update_contest_team_members_status(
            contest_team_id=contest_team.id,
            from_statuses=[
                ContestTeamMemberStatus.INVITED,
                ContestTeamMemberStatus.ACCEPTED,
            ],
            to_status=ContestTeamMemberStatus.CANCELLED,
            exclude_user_id=exclude_user_id,
        )

        contest_team.team_status = TeamStatus.CANCELLED
        contest_team.approval_status = TeamApprovalStatus.CANCELLED
        contest_team.leader_id = None
        await self.repository.update_contest_team(contest_team)

    async def _handle_member_removed(
        self,
        user_id: UUID,
        contest_team: ContestTeam,
        contest_team_member: ContestTeamMember,
    ) -> None:
        """Helper to handle removing a team member by the leader."""
        # Check if the user is the leader of the team
        self.team_student_guard.check_is_contest_team_leader(
            contest_team=contest_team, user_id=user_id
        )

        # The team leader cannot remove themselves
        if contest_team_member.user_id == contest_team.leader_id:
            raise CannotRemoveTeamLeaderError(
                team_name=contest_team.team.name
                if contest_team.team
                else contest_team.name
            )

    async def _handle_member_left(
        self,
        user_id: UUID,
        contest_team_id: UUID,
        contest_team: ContestTeam,
        contest_team_member: ContestTeamMember,
    ) -> None:
        """Helper to handle a team member leaving the team."""
        # A member can only leave for themselves
        if contest_team_member.user_id != user_id:
            raise TeamMemberAccessDeniedError(
                team_id=str(contest_team.id), user_id=str(user_id)
            )

        # If the leaving user is the current leader
        if contest_team.leader_id == contest_team_member.user_id:
            # Find all accepted members
            all_accepted = await self.repository.get_contest_team_members(
                contest_team_id, [ContestTeamMemberStatus.ACCEPTED]
            )
            other_accepted = [
                m for m in all_accepted if m.user_id != contest_team_member.user_id
            ]

            if other_accepted:
                # Sort other_accepted members to find the earliest accepted member
                late_datetime = datetime.max.replace(tzinfo=timezone.utc)
                other_accepted.sort(
                    key=lambda m: (
                        m.confirmed_at if m.confirmed_at is not None else late_datetime
                    )
                )
                new_leader = other_accepted[0]
                contest_team.leader_id = new_leader.user_id
                await self.repository.update_contest_team(contest_team)
            else:
                # If the leader is the last person to leave the team, cancel the team status
                await self._cancel_contest_team(
                    contest_team, exclude_user_id=contest_team_member.user_id
                )

    async def _handle_member_accepted(
        self,
        user_id: UUID,
        contest_team_id: UUID,
        contest_team: ContestTeam,
        contest_team_member: ContestTeamMember,
        contest: Contest,
    ) -> None:
        """Helper to handle a team member accepting an invite."""
        # A user can only accept their own invitation
        if contest_team_member.user_id != user_id:
            raise TeamMemberAccessDeniedError(
                team_id=str(contest_team.id), user_id=str(user_id)
            )

        # Check if the user is already in the contest
        await self.contest_student_guard.check_student_already_in_contest(
            contest_id=contest.id,
            user_ids=[user_id],
        )
        await self._ensure_students_have_not_started_session(
            contest_id=contest.id,
            user_ids=[user_id],
        )

        # Locked so two invitees accepting for this same team at the same
        # moment can't both pass the count check before either status write
        # commits (see acquire_roster_lock docstring). The lock is held for
        # the rest of this request's transaction, which covers the actual
        # status write performed later by the caller.
        await self.repository.acquire_roster_lock(contest_team_id)
        current_contest_team_member_count = (
            await self.repository.count_contest_team_members(
                contest_team_id, ContestTeamMemberStatus.ACCEPTED
            )
        )
        # Check if team is full (i.e. size is already at or above max_team_size)
        if current_contest_team_member_count >= contest.max_team_size:
            raise InvalidTeamSizeError(
                size=current_contest_team_member_count + 1,
                min_size=contest.min_team_size,
                max_size=contest.max_team_size,
            )

    async def invite_members(
        self,
        contest_id: UUID,
        contest_team_id: UUID,
        invite_user_ids: list[UUID],
        user_id: UUID,
    ) -> None:
        """
        Invite members to a contest team.

        Args:
            contest_id: UUID of the contest.
            team_id: UUID of the team.
            contest_team_id: UUID of the contest team.
            invite_user_ids: list of student UUIDs to invite.
            user_id: UUID of the current user initiating the invite.
        """
        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        contest_team = await self.repository.get_contest_team_by_id_or_raise(
            contest_team_id
        )

        TeamValidator.validate_team_operations_allowed(
            contest.contest_mode, "invite members"
        )

        # Validate registration timeframe
        ContestValidator.validate_registration_date_past(
            contest.registration_start, contest.registration_end
        )

        # Validate that the contest team belongs to this contest
        if contest_team.contest_id != contest_id:
            raise ContestTeamNotFoundException(str(contest_team_id))

        # Validate team status (must be DRAFT)
        if contest_team.team_status != TeamStatus.DRAFT:
            raise TeamStatusNotAllowedForUpdatingContestTeamMemberStatusException()

        # Validate requester is the contest team leader
        self.team_student_guard.check_is_contest_team_leader(
            user_id=user_id, contest_team=contest_team
        )

        # Validate underlying team membership constraint if team_id is set
        team_member_ids: set[UUID] = set()
        if contest_team.team_id is not None:
            members_data = await self.team_repository.get_team_members(
                team_id=contest_team.team_id
            )
            team_member_ids = {row[0].id for row in members_data}

        ContestTeamValidator.validate_team_membership_if_needed(
            team_id=contest_team.team_id,
            team_member_ids=team_member_ids,
            invitee_ids=invite_user_ids,
            team_name=contest_team.name,
        )

        # Validate team size capacity limits. Locked so a concurrent invite
        # or accept for this same team can't slip past the count check
        # before this one's inserts commit (see acquire_roster_lock
        # docstring).
        await self.repository.acquire_roster_lock(contest_team_id)
        active_members_count = await self.repository.count_contest_team_members(
            contest_team_id,
            [ContestTeamMemberStatus.INVITED, ContestTeamMemberStatus.ACCEPTED],
        )
        total_prospective_size = active_members_count + len(invite_user_ids)
        if total_prospective_size > contest.max_team_size:
            raise InvalidTeamSizeError(
                size=total_prospective_size,
                min_size=contest.min_team_size,
                max_size=contest.max_team_size,
            )

        # Validate that none of the invitees are already pending or accepted in this team
        existing_members = await self.repository.get_contest_team_members(
            contest_team_id=contest_team_id,
            user_ids=invite_user_ids,
        )
        for member in existing_members:
            if member.status in (
                ContestTeamMemberStatus.INVITED,
                ContestTeamMemberStatus.ACCEPTED,
            ):
                raise MemberAlreadyInTeamError(
                    user_id=str(member.user_id), team_name=contest_team.name
                )

        # Validate that invitees are not already active in the contest (ACCEPTED or INVITED in any team)
        active_in_contest = await self.repository.get_active_members_in_contest(
            contest_id=contest_id,
            user_ids=invite_user_ids,
        )
        if active_in_contest:
            active_uids = [str(m.user_id) for m in active_in_contest]
            raise StudentAlreadyInContestError(
                user_id=", ".join(active_uids), contest_id=str(contest_id)
            )

        # Validate student audience eligibility for the contest
        if not contest.is_public:
            await self.contest_student_guard.check_student_audiences_for_contest(
                user_ids=invite_user_ids,
                contest_id=contest_id,
            )

        # Create ContestTeamMember records
        new_members = [
            ContestTeamMember(
                contest_id=contest_id,
                contest_team_id=contest_team_id,
                user_id=uid,
                status=ContestTeamMemberStatus.INVITED,
            )
            for uid in invite_user_ids
        ]
        await self.repository.create_contest_team_members(new_members)

    async def get_contest_leaderboard(
        self,
        contest_id: UUID,
        user_id: UUID,
        search_term: str | None = None,
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[LeaderboardResponse, int]:
        """Get the contest leaderboard for a student, gated by result visibility.

        Reuses the same cached computation as the instructor-facing
        leaderboard (``get_cached_contest_leaderboard``), and additionally
        surfaces the requesting student's own team rank/score (which may
        fall outside the requested page).

        Args:
            contest_id: UUID of the contest.
            user_id: UUID of the student requesting the leaderboard.
            search_term: Optional name filtering term.
            sort_order: Sorting order ('asc' or 'desc').
            skip: Number of teams to skip.
            limit: Maximum number of teams to return.

        Raises:
            ContestNotFoundError: If the contest does not exist or is deleted.
            StudentNotEligibleForContestError: If the student lacks audience access.
            ContestResultsNotVisibleError: If results are hidden or team-only.
        """
        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        ContestValidator.validate_not_deleted(contest.status, contest_id)

        await self.contest_student_guard.check_student_eligibility(
            user_id=user_id, contest=contest
        )

        if not contest.results_published_at or not contest.show_leaderboard:
            raise ContestResultsNotVisibleError(str(contest_id))

        is_leader_only = (
            contest.participation_type == ContestTeamParticipationType.LEADER_ONLY
        )
        leaderboard, total = await ContestService.get_cached_contest_leaderboard(
            self.contest_repository,
            contest_id,
            search_term,
            sort_order,
            skip,
            limit,
            is_leader_only,
        )

        return leaderboard, total

    async def _get_own_contest_team_id(
        self, contest_id: UUID, user_id: UUID
    ) -> UUID | None:
        """Look up the caller's own accepted contest team membership, if any."""
        member = await self.repository.get_contest_team_member_by_user_id(
            user_id=user_id,
            contest_id=contest_id,
            status=ContestTeamMemberStatus.ACCEPTED,
        )
        if not member or not member.contest_team:
            return None
        return member.contest_team_id

    async def _check_member_belongs_to_my_team(
        self, contest_id: UUID, contest_team_member_id: UUID, user_id: UUID
    ) -> UUID:
        """Ensure the target member is part of the caller's own contest team.

        Returns:
            The caller's contest_team_id.

        Raises:
            TeamMemberAccessDeniedError: If the caller has no team in this contest,
                or the target member belongs to a different team.
        """
        own_team_id = await self._get_own_contest_team_id(contest_id, user_id)
        if own_team_id is None:
            raise TeamMemberAccessDeniedError(
                team_id=str(contest_id), user_id=str(user_id)
            )

        target_member = await self.repository.get_contest_team_member_or_raise(
            contest_team_member_id
        )
        if target_member.contest_team_id != own_team_id:
            raise TeamMemberAccessDeniedError(
                team_id=str(own_team_id), user_id=str(user_id)
            )

        return own_team_id

    async def _check_team_results_visible(self, contest_id: UUID) -> None:
        """Ensure contest results are published with team submissions visible.

        Raises:
            ContestNotFoundError: If the contest does not exist or is deleted.
            ContestResultsNotVisibleError: If results are unpublished or
                team submissions are not configured to be shown.
        """
        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        ContestValidator.validate_not_deleted(contest.status, contest_id)

        if not contest.results_published_at:
            raise ContestResultsNotVisibleError(str(contest_id))

    async def get_my_team_results(
        self, contest_id: UUID, user_id: UUID
    ) -> StudentTeamAnalytics | None:
        """Get score, participation, and submission analytics for the caller's team.

        Args:
            contest_id: UUID of the contest.
            user_id: UUID of the student requesting their team's results.

        Returns:
            StudentTeamAnalytics for the student's contest team, or None if the
            student has no accepted team membership in this contest.

        Raises:
            ContestNotFoundError: If the contest does not exist or is deleted.
            ContestResultsNotVisibleError: If results are unpublished or
                team submissions are not configured to be shown.
        """
        await self._check_team_results_visible(contest_id)

        own_team_id = await self._get_own_contest_team_id(contest_id, user_id)
        if own_team_id is None:
            return None

        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        is_leader_only = (
            contest.participation_type == ContestTeamParticipationType.LEADER_ONLY
        )
        assert self.team_analytics_repository is not None
        (
            team_row,
            member_rows,
        ) = await self.team_analytics_repository.get_contest_team_analytics(
            contest_id, own_team_id, is_leader_only=is_leader_only
        )
        return to_student_team_analytics(team_row, member_rows)

    async def get_team_member_results(
        self, contest_id: UUID, contest_team_member_id: UUID, user_id: UUID
    ) -> StudentMemberDetail:
        """Get detail, session timing, and aggregate stats for a member of the caller's team."""
        await self._check_team_results_visible(contest_id)

        own_team_id = await self._check_member_belongs_to_my_team(
            contest_id, contest_team_member_id, user_id
        )

        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        is_leader_only = (
            contest.participation_type == ContestTeamParticipationType.LEADER_ONLY
        )
        assert self.team_analytics_repository is not None
        member_row = (
            await self.team_analytics_repository.get_contest_team_member_detail(
                contest_id=contest_id,
                contest_team_id=own_team_id,
                contest_team_member_id=contest_team_member_id,
                is_leader_only=is_leader_only,
            )
        )
        return to_student_member_detail(member_row)

    async def get_team_member_question_analytics(
        self, contest_id: UUID, contest_team_member_id: UUID, user_id: UUID
    ) -> list[StudentMemberQuestionAnalytics]:
        """Get all contest questions with submission counts for a member of the caller's team."""
        await self._check_team_results_visible(contest_id)

        own_team_id = await self._check_member_belongs_to_my_team(
            contest_id, contest_team_member_id, user_id
        )

        assert self.team_analytics_repository is not None
        question_rows = await self.team_analytics_repository.get_contest_team_member_question_analytics(
            contest_id=contest_id,
            contest_team_id=own_team_id,
            contest_team_member_id=contest_team_member_id,
        )
        return to_student_member_question_analytics(question_rows)

    async def get_team_member_question_submissions(
        self,
        contest_id: UUID,
        contest_team_member_id: UUID,
        question_id: UUID,
        user_id: UUID,
    ) -> StudentMemberQuestionSubmissions:
        """Get submissions and verdict stats for one question by a member of the caller's team."""
        await self._check_team_results_visible(contest_id)

        own_team_id = await self._check_member_belongs_to_my_team(
            contest_id, contest_team_member_id, user_id
        )

        assert self.team_analytics_repository is not None
        (
            question_row,
            stats_row,
            submission_rows,
        ) = await self.team_analytics_repository.get_contest_team_member_question_submissions(
            contest_id=contest_id,
            contest_team_id=own_team_id,
            contest_team_member_id=contest_team_member_id,
            question_id=question_id,
        )
        return to_student_member_question_submissions(
            question_row, stats_row, submission_rows
        )
