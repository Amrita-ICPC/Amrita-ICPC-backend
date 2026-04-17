"""Student-facing service for team operations.

This service orchestrates student team-related business logic by coordinating
between the repository layer (data access) and schema layer (response formatting).
It focuses on team discovery, creation, joining, and membership management
from a student's perspective.

Architecture:
    - Repository Pattern: All database operations delegated to TeamRepository
    - No Guard/Validator: Students have broad read access, limited write access
    - Cache Strategy: Results cached with appropriate TTLs and user context

Key Responsibilities:
    - Query teams user is a member of
    - Query available teams to join in a contest
    - Get team details with members
    - Create new teams for contests
    - Join existing teams
    - Add members to team (leader only)
    - Remove members from team (leader only)
    - Leave teams
    - Transform repository data to API response schemas
    - Coordinate cache invalidation for team-related data
"""

from typing import TYPE_CHECKING
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get
from app.core.logger import logger
from app.exceptions.auth import PermissionDeniedError
from app.exceptions.student.teams import TeamNotFoundError
from app.mappers.student.team_mappers import (
    to_student_available_teams_list_response,
    to_student_team_create_and_join_response,
    to_student_team_join_response,
    to_student_team_response,
    to_student_teams_list_response,
)
from app.repositories.dto import PaginationParams
from app.schema.student.teams import (
    StudentLeaveTeamResponse,
    StudentTeamAddMemberResponse,
    StudentTeamCreateAndJoinResponse,
    StudentTeamCreateRequest,
    StudentTeamJoinResponse,
    StudentTeamListResponse,
    StudentTeamMemberResponse,
    StudentTeamRemoveMemberResponse,
    StudentTeamResponse,
)

if TYPE_CHECKING:
    from app.repositories.team import TeamRepository


def get_student_team_key(team_id: UUID, user_id: UUID) -> str:
    """Generate cache key for student team view."""
    return f"student:team:{team_id}:user:{user_id}"


class StudentTeamService:
    """Service layer for student team operations.

    Orchestrates student-specific team queries and membership operations.
    Focuses on team discovery and participation from student perspective.

    Architecture:
        - Repository Pattern: All database operations delegated to TeamRepository
        - No Guard/Validator: Students can discover and join teams with basic rules
        - Cache Strategy: Individual and list queries cached with user context

    Key Methods:
        - get_my_teams: Query teams user is member of
        - get_team_by_id: Get team details with members
        - get_available_teams_in_contest: Find teams available to join
        - create_and_join_team: Create new team and join contest
        - join_team: Request or directly join existing team
        - leave_team: Remove self from team

    Cache Strategy:
        - User's teams cached per student
        - Team details cached per student per team
        - Available teams cached per contest per student
        - Cache invalidated on membership changes
    """

    def __init__(self, team_repository: "TeamRepository"):
        self.repository = team_repository

    @cache_get(
        key_builder=lambda self,
        user_id,
        skip=0,
        limit=10: f"student:teams:user:{user_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_my_teams(
        self, user_id: UUID, skip: int = 0, limit: int = 10
    ) -> StudentTeamListResponse:
        """
        Get all teams the student is a member of.

        Retrieves teams via TeamUser join table where current user is a member.
        Includes team details, member counts, and leader information.

        Implementation:
        - Queries via TeamUser relationship
        - Fetches each team with member details
        - Includes leader identification for each team
        - Supports pagination

        Args:
            user_id: UUID of the student
            skip: Number of teams to skip for pagination (default: 0)
            limit: Maximum teams to return (default: 10, max: 100)

        Returns:
            StudentTeamListResponse with list of teams and total count

        Cache Behavior:
            - Cached per student
            - TTL: 300 seconds
        """
        pagination = PaginationParams(skip=skip, limit=limit)

        result = await self.repository.get_user_teams(
            user_id=user_id, pagination=pagination
        )

        logger.info(f"Student {user_id} queried their teams (found: {result.total})")
        return to_student_teams_list_response(result, skip, limit, user_id)

    @cache_get(
        key_builder=lambda self, team_id, user_id: get_student_team_key(
            team_id, user_id
        ),
        ttl=300,
    )
    async def get_team_by_id(self, team_id: UUID, user_id: UUID) -> StudentTeamResponse:
        """
        Get complete team details with all members.

        Retrieves team information including:
        - Team metadata (name, description, created_at)
        - All team members with names and emails
        - Leader identification
        - Current user's relationship to team (member, leader status)

        Implementation:
        - Fetches team via repository
        - Fetches all team members with user details
        - Determines user's role in team
        - Constructs detailed response

        Args:
            team_id: UUID of the team
            user_id: UUID of the student viewing

        Returns:
            StudentTeamResponse with team details and members

        Raises:
            TeamNotFoundError: If team not found

        Cache Behavior:
            - Cached per student per team
            - TTL: 300 seconds
        """
        team = await self.repository.get_team_or_raise(team_id)

        # Fetch team members with details
        members = await self.repository.get_team_members_detailed(team_id)

        logger.info(f"Student {user_id} viewed team {team_id} details")
        return to_student_team_response(team, members, user_id)

    @cache_get(
        key_builder=lambda self,
        contest_id,
        user_id,
        skip=0,
        limit=10: f"student:contest:{contest_id}:teams:available:user:{user_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_available_teams_in_contest(
        self,
        contest_id: UUID,
        user_id: UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> "StudentTeamListResponse":
        """
        Get teams available to join in a specific contest.

        Retrieves teams in the contest that have available slots:
        - Team has fewer members than max_team_size for contest
        - Team is not full
        - Team is confirmed for the contest
        - Current user is not already a member

        Implementation:
        - Fetches contest to get max_team_size
        - Queries teams in contest with available slots
        - Filters out teams user is already in
        - Supports pagination

        Args:
            contest_id: UUID of the contest
            user_id: UUID of the student looking to join (for filtering)
            skip: Number of teams to skip (default: 0)
            limit: Maximum teams to return (default: 10)

        Returns:
            Paginated list response of available teams

        Raises:
            ContestNotFoundError: If contest not found

        Cache Behavior:
            - Cached per contest per student
            - TTL: 300 seconds
        """
        contest = await self.repository.get_contest_or_raise(contest_id)

        result = await self.repository.get_available_teams_in_contest(
            contest_id=contest_id,
            skip=skip,
            limit=limit,
        )

        logger.info(
            f"Student {user_id} queried available teams in contest {contest_id} (found: {len(result)})"
        )
        return to_student_available_teams_list_response(
            result, max_team_size=contest.max_team_size, current_user_id=user_id
        )

    @cache_delete(
        key_builder=lambda self, contest_id, team_data, created_by: [
            f"student:teams:user:{created_by}:*",
            f"student:contest:{contest_id}:teams:available:user:{created_by}:*",
        ]
    )
    async def create_and_join_team(
        self,
        contest_id: UUID,
        team_data: StudentTeamCreateRequest,
        created_by: UUID,
    ) -> StudentTeamCreateAndJoinResponse:
        """
        Create a new team and register it in a contest.

        Creates a new team with student as the sole member and leader,
        then registers the team in the specified contest. The team is
        immediately set to CONFIRMED status.

        Business Rules:
        1. Contest MUST be PUBLIC (students cannot create teams for private contests)
        2. Contest MUST exist and not be soft-deleted
        3. Student becomes team creator and leader

        Approval Status:
        - AUTO_APPROVE: Team approved automatically
        - INSTRUCTOR_REVIEW: Team waiting for instructor approval

        Process:
        1. Validate contest exists and is not soft-deleted
        2. Verify contest is PUBLIC (critical business rule)
        3. Create team with student as creator and leader
        4. Create ContestTeam record with contest
        5. Create ContestTeamProgress for tracking
        6. Return response with team and approval status

        Implementation:
        - Checks contest.is_public before allowing team creation
        - Uses repository create_student_team_for_contest method
        - Automatically adds creator as member and leader
        - Sets initial approval status based on contest settings
        - Invalidates student's team lists

        Args:
            contest_id: UUID of the contest to register team in
            team_data: StudentTeamCreateRequest with team_name and optional description
            created_by: UUID of the student creating the team

        Returns:
            StudentTeamCreateAndJoinResponse with new team details

        Raises:
            ContestNotFoundError: If contest not found or soft-deleted
            PermissionDeniedError: If contest is not public
            TeamAlreadyExistsError: If team name conflicts in contest

        Cache Behavior:
            - Invalidates student's teams list
            - Invalidates available teams in contest
        """
        contest = await self.repository.get_contest_or_raise(contest_id)

        if contest.is_deleted:
            raise TeamNotFoundError(str(contest_id), str(contest_id))

        # CRITICAL BUSINESS RULE: Students can only create teams for PUBLIC contests
        if not contest.is_public:
            raise PermissionDeniedError(
                f"Cannot create teams for private contests. Contest '{contest.name}' is not public."
            )

        # Create team and register in contest
        (
            team,
            contest_team,
            progress,
            team_user,
        ) = await self.repository.create_student_team_for_contest(
            team_name=team_data.name,
            team_description=team_data.description,
            contest_id=contest_id,
            created_by=created_by,
        )

        logger.info(
            f"Student {created_by} created team '{team.name}' and registered for contest {contest_id}"
        )

        return to_student_team_create_and_join_response(
            team_id=team.id,
            team_name=team.name,
            contest_id=contest_id,
            approval_status=contest_team.approval_status,
        )

    @cache_delete(
        key_builder=lambda self, team_id, contest_id, user_id: [
            f"student:team:{team_id}:user:{user_id}",
            f"student:teams:user:{user_id}:*",
        ]
    )
    async def join_team(
        self,
        team_id: UUID,
        contest_id: UUID,
        user_id: UUID,
    ) -> StudentTeamJoinResponse:
        """
        Join an existing team in a contest.

        Adds the student to an existing team and ensures the team is
        registered in the contest if not already.

        Join Process:
        1. Validate team exists
        2. Validate contest exists
        3. Validate team has available slots
        4. Check student not already member
        5. Add student to team (creates TeamUser)
        6. Ensure team is registered in contest (creates ContestTeam if needed)
        7. Return join response with approval status

        Approval Status from contest:
        - AUTO_APPROVE: Student immediately participating
        - INSTRUCTOR_REVIEW: Student waiting for team approval

        Implementation:
        - Uses repository add_student_to_team method
        - Validates team size constraints before adding
        - Handles team contest registration
        - Invalidates team caches

        Args:
            team_id: UUID of the team to join
            contest_id: UUID of the contest context
            user_id: UUID of the student joining

        Returns:
            StudentTeamJoinResponse with join status

        Raises:
            TeamNotFoundError: If team not found
            ContestNotFoundError: If contest not found
            TeamFullError: If team is at max size
            StudentAlreadyInTeamError: If student is already member
            InvalidTeamSizeError: If team addition violates constraints

        Cache Behavior:
            - Invalidates student's teams list
            - Invalidates student's team details cache
        """
        team = await self.repository.get_team_or_raise(team_id, contest_id)

        await self.repository.get_contest_or_raise(contest_id)

        # Add student to team (validates size and membership)
        await self.repository.add_student_to_team(team_id=team_id, user_id=user_id)

        logger.info(f"Student {user_id} joined team {team_id} in contest {contest_id}")

        return to_student_team_join_response(
            team_id=team.id,
            team_name=team.name,
            contest_id=contest_id,
        )

    @cache_delete(
        key_builder=lambda self, team_id, user_id: [
            f"student:team:{team_id}:user:{user_id}",
            f"student:teams:user:{user_id}:*",
        ]
    )
    async def leave_team(
        self, team_id: UUID, user_id: UUID
    ) -> StudentLeaveTeamResponse:
        """
        Remove student from a team.

        Removes the student as a member from the team. Prevents removal
        if student is the team leader (must transfer leadership first).

        Leave Process:
        1. Validate team exists
        2. Validate student is team member
        3. Check student is not team leader
        4. Remove student from team (delete TeamUser)
        5. Return success response

        Leadership Requirement:
        - If student is leader, must reassign leadership before leaving
        - Prevents teams from losing all leadership

        Implementation:
        - Uses repository remove_student_from_team method
        - Validates member and leader status
        - Handles edge cases (last member, leader removal)
        - Invalidates team caches

        Args:
            team_id: UUID of the team to leave
            user_id: UUID of the student leaving

        Returns:
            StudentLeaveTeamResponse with leave status

        Raises:
            TeamNotFoundError: If team not found
            MemberNotInTeamError: If student not in team
            CannotRemoveTeamLeaderError: If student is team leader

        Cache Behavior:
            - Invalidates student's teams list
            - Invalidates team details caches
        """
        team = await self.repository.get_team_or_raise(team_id)

        # Validate student is member
        is_member = await self.repository.is_student_in_team(team_id, user_id)
        if not is_member:
            raise PermissionDeniedError("You are not a member of this team")

        # Check student is not leader
        if team.leader_id == user_id:
            return StudentLeaveTeamResponse(
                message="Cannot leave team as leader. Transfer leadership first.",
                team_id=team_id,
                status="cannot_leave_leader",
            )

        # Remove from team
        await self.repository.remove_student_from_team(team_id, user_id)

        logger.info(f"Student {user_id} left team {team_id}")

        return StudentLeaveTeamResponse(
            message="Successfully left team",
            team_id=team_id,
            status="success",
        )

    async def add_member_to_team(
        self,
        team_id: UUID,
        leader_user_id: UUID,
        member_ids: list[UUID],
    ) -> StudentTeamAddMemberResponse:
        """
        Add members to a team (leader only).

        Adds new students to an existing team. Only team leaders can add members.
        Follows the same strategy as the regular TeamService.add_team_members.

        Validation Flow (identical to TeamService.add_team_members):
        1. Get team and verify leader authorization
        2. Get all existing team members
        3. Get contest via ContestTeam join
        4. Validate team size won't exceed maximum after adding members
        5. Validate all member user IDs exist in database
        6. Validate no duplicate memberships
        7. Add members via repository
        8. Return updated member list

        Business Rules:
        1. Only team leader can add members
        2. Team must not exceed max_team_size after adding
        3. All user IDs must exist in database
        4. No user can be added twice
        5. Members cannot already be in the team

        Args:
            team_id: UUID of team to add members to
            leader_user_id: UUID of user making request (must be leader)
            member_ids: List of user IDs to add to team

        Returns:
            StudentTeamAddMemberResponse with added members and team details

        Raises:
            TeamNotFoundError: If team not found
            PermissionDeniedError: If requester is not team leader
            UserNotFoundError: If any specified member does not exist
            ValueError: If duplicate members or already in team
        """
        from sqlalchemy import select

        from app.models.contest import Contest, ContestTeam

        # Step 1: Get team and verify requester is leader
        team = await self.repository.get_team_or_raise(team_id)

        if team.leader_id != leader_user_id:
            raise PermissionDeniedError("Only team leader can add members")

        # Step 2: Get existing team members count
        existing_team_members = await self.repository.get_all_team_members(team_id)
        current_count = len(existing_team_members)
        new_members_count = len(member_ids)

        # Step 3: Get contest for this team via direct query
        # Query: Contest <- ContestTeam where team_id = ?
        contest = await self.repository.db.execute(
            select(Contest)
            .join(ContestTeam, Contest.id == ContestTeam.contest_id)
            .filter(ContestTeam.team_id == team_id)
        )
        contest_record = contest.scalars().first()
        if not contest_record:
            raise ValueError("Team is not registered in any contest")

        # Step 4: Validate team size constraint
        if current_count + new_members_count > contest_record.max_team_size:
            raise ValueError(
                f"Adding {new_members_count} members would exceed team limit of {contest_record.max_team_size}"
            )

        # Step 5: Validate all users exist
        await self.repository.get_users_or_raise(user_ids=member_ids)

        # Step 6: Validate members are not already in team
        existing_member_ids = {tu.user_id for tu in existing_team_members}
        already_members = set(member_ids) & existing_member_ids
        if already_members:
            raise ValueError("Some members are already in the team")

        # Step 7: Add members via repository
        await self.repository.add_team_members(
            team_id=team_id,
            member_ids=member_ids,
            leader_id=None,  # Don't change leader when adding members
        )

        logger.info(
            f"User {leader_user_id} added {len(member_ids)} members to team {team_id}"
        )

        # Step 8: Fetch and return updated member list
        updated_members = await self.repository.get_team_members_detailed(team_id)
        member_responses = [
            StudentTeamMemberResponse(
                id=tu.user_id,
                name=tu.user.name,
                email=tu.user.email,
                is_leader=team.leader_id == tu.user_id,
            )
            for tu in updated_members
        ]

        return StudentTeamAddMemberResponse(
            message=f"Successfully added {len(member_ids)} members to team",
            team_id=team_id,
            added_count=len(member_ids),
            total_member_count=current_count + new_members_count,
            members=member_responses,
            status="success",
        )

    async def remove_member_from_team(
        self,
        team_id: UUID,
        leader_user_id: UUID,
        member_user_id: UUID,
    ) -> StudentTeamRemoveMemberResponse:
        """
        Remove a member from a team (leader only).

        Removes a student from a team. Only team leaders can remove members.
        Prevents removal of the team leader (leader must resign first).

        Business Rules:
        1. Only team leader can remove members
        2. Cannot remove the team leader
        3. Member must exist in team
        4. Cannot leave team empty

        Remove Process:
        1. Verify requester is team leader
        2. Check member is not team leader
        3. Verify member is in team
        4. Remove member from team
        5. Invalidate team caches

        Implementation:
        - Checks team.leader_id == requester
        - Prevents leader removal
        - Uses repository remove_student_from_team

        Args:
            team_id: UUID of team to remove member from
            leader_user_id: UUID of user making request (must be leader)
            member_user_id: UUID of user to remove from team

        Returns:
            StudentTeamRemoveMemberResponse with remove status

        Raises:
            TeamNotFoundError: If team not found
            PermissionDeniedError: If requester is not team leader OR trying to remove leader
            MemberNotInTeamError: If user not in team

        Cache Behavior:
            - Invalidates team details cache
            - Invalidates team member list
        """
        team = await self.repository.get_team_or_raise(team_id)

        # CRITICAL: Only team leader can remove members
        if team.leader_id != leader_user_id:
            raise PermissionDeniedError("Only team leader can remove members")

        # Get member to remove
        members = await self.repository.get_team_members_detailed(team_id)
        team_user = next(
            (tu for tu in members if tu.user_id == member_user_id),
            None,
        )
        if team_user is None:
            raise PermissionDeniedError("User is not a member of this team")

        # Cannot remove team leader
        if team.leader_id == member_user_id:
            return StudentTeamRemoveMemberResponse(
                message="Cannot remove team leader. Reassign leadership first.",
                team_id=team_id,
                removed_user_id=member_user_id,
                status="cannot_remove_leader",
            )

        # Remove member from team
        await self.repository.remove_student_from_team(team_id, member_user_id)

        # Get updated member count (for logging only)
        await self.repository.get_all_team_members(team_id)

        logger.info(
            f"User {leader_user_id} removed {member_user_id} from team {team_id}"
        )

        return StudentTeamRemoveMemberResponse(
            message="Successfully removed member from team",
            team_id=team_id,
            removed_user_id=member_user_id,
            status="success",
        )
