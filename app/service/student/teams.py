"""Student-facing service for team operations.

This service duplicates TeamService patterns for student-specific operations.
Follows exact architecture of TeamService but with student-only semantics.

Architecture:
    - Repository Pattern: All database operations delegated to TeamRepository
    - Guard Pattern: Centralized permission checks via TeamOperationGuard  
    - Validator Pattern: Business rule validation via TeamValidator
    - Mapper Pattern: All ORM → DTO/Schema transformations via dedicated mappers
    - Cache Strategy: Results cached with appropriate TTLs and user context

Key Responsibilities:
    - Query teams user is member of
    - Query available teams to join in contest
    - Get team details with members
    - Create new teams for contests
    - Join existing teams (pending/approved)
    - Add members to team (leader only)
    - Remove members from team (leader only)
    - Leave teams (with leader succession handling)
    - Coordinate cache invalidation

Cache Strategy:
    - User's teams: Cached per user per pagination
    - Team details: Cached per user per team
    - Available teams: Cached per user per contest
    - Cache invalidated on team mutations
"""

from typing import TYPE_CHECKING, cast
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get
from app.core.guards.team import TeamOperationGuard
from app.core.logger import logger
from app.exceptions.auth import PermissionDeniedError
from app.exceptions.student.teams import (
    TeamNotFoundError,
    MemberAlreadyInTeamError,
    InvalidTeamSizeError,
)
from app.mappers.student.team_mappers import (
    to_student_team_member_response,
    to_student_team_response,
    to_student_teams_list_response,
)
from app.repositories.dto import PaginationParams
from app.schema.student.teams import (
    StudentTeamAddMemberRequest,
    StudentTeamAddMemberResponse,
    StudentTeamCreateAndJoinResponse,
    StudentTeamCreateRequest,
    StudentTeamCreateResponse,
    StudentTeamJoinRequest,
    StudentTeamJoinResponse,
    StudentLeaveTeamResponse,
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
    Follows TeamService architecture with student-appropriate access levels.

    Architecture:
        - Repository Pattern: All DB operations via TeamRepository
        - Guard Pattern: Permission checks via TeamOperationGuard
        - Validator Pattern: Business rules via TeamValidator
        - Mapper Pattern: ORM transformations via dedicated mappers
        - Cache Strategy: Permission-aware caching per user

    Dependencies:
        - TeamRepository: Team data access
        - TeamOperationGuard: Permission validation  
        - TeamValidator: Business rule validation

    Cache Strategy:
        - User's teams: Per user per pagination
        - Team details: Per user per team
        - Team members: Per user per team per pagination
        - Available teams: Per user per contest
        - Cache invalidated on mutations
    """

    def __init__(
        self,
        team_repository: "TeamRepository",
        guard: TeamOperationGuard,
        validator=None,  # May not be needed for student operations
    ):
        self.repository = team_repository
        self.guard = guard
        self.validator = validator

    @cache_get(
        key_builder=lambda self, user_id, skip=0, limit=10: (
            f"student:teams:user:{user_id}:skip:{skip}:limit:{limit}"
        ),
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
        - Includes leader identification
        - Supports pagination

        Args:
            user_id: UUID of the student
            skip: Pagination skip (default: 0)
            limit: Pagination limit (default: 10, max: 100)

        Returns:
            StudentTeamListResponse with paginated team list

        Cache Behavior:
            - Cached per user including pagination
            - TTL: 300 seconds
        """
        pagination = PaginationParams(skip=skip, limit=limit)

        result = await self.repository.get_user_teams(
            user_id=user_id, pagination=pagination
        )

        logger.info(f"Student {user_id} queried their teams (found: {result.total})")
        return to_student_teams_list_response(result, skip, limit, user_id)

    @cache_get(
        key_builder=lambda self, team_id, user_id: get_student_team_key(team_id, user_id),
        ttl=300,
    )
    async def get_team_by_id(
        self, team_id: UUID, user_id: UUID
    ) -> StudentTeamResponse:
        """
        Get complete team details with all members.

        Retrieves team information including:
        - Team metadata (name, description, created_at)
        - All team members with names and emails
        - Leader identification
        - Current user's team role (member, leader)

        Implementation:
        - Fetches team via repository
        - Fetches all team members with user details  
        - Determines user's role in team
        - Transforms to detailed response

        Args:
            team_id: UUID of the team
            user_id: UUID of the student viewing

        Returns:
            StudentTeamResponse with full team details

        Raises:
            TeamNotFoundError: If team not found

        Cache Behavior:
            - Cached per user per team
            - TTL: 300 seconds
        """
        team = await self.repository.get_team_or_raise(team_id)

        team_members = await self.repository.get_team_members_detailed(team_id)

        logger.info(f"Student {user_id} viewed team {team_id}")
        return to_student_team_response(team, team_members, user_id)

    @cache_delete(
        key_builder=lambda self, contest_id, team_data, created_by: [
            f"student:teams:user:{created_by}:*",
            f"student:contests:{contest_id}:teams:available:*",
        ]
    )
    async def create_and_join_team(
        self, 
        contest_id: UUID, 
        team_data: StudentTeamCreateRequest, 
        created_by: UUID,
    ) -> StudentTeamCreateAndJoinResponse:
        """
        Create a new team for a contest and join it.

        Creates a team and registers it for a contest with the creator as leader.
        Student becomes initial member and automatic owner.

        Validation Flow:
        1. Verify contest exists  
        2. Verify user has permission to create team in contest
        3. Verify team name is unique within contest
        4. Verify user exists in database
        5. Create Team, ContestTeam, TeamUser records
        6. Invalidate team caches

        Business Rules:
        1. Team name must be unique per contest
        2. User becomes team leader automatically
        3. Team starts in DRAFT status
        4. Team registered for contest immediately
        5. User is automatically included as first member

        Args:
            contest_id: UUID of the contest
            team_data: StudentTeamCreateRequest with name, description
            created_by: UUID of the student creating team

        Returns:
            StudentTeamCreateAndJoinResponse with created team details

        Raises:
            ContestNotFoundError: If contest not found
            PermissionDeniedError: If user lacks permission
            TeamAlreadyExistsError: If name not unique
            UserNotFoundError: If user not found

        Cache Behavior:
            - Invalidates user's team list
            - Invalidates contest's available teams
        """
        # Delegate most of this to repository since it handles the entity creation
        from app.models.team import Team, TeamUser
        from app.models.contest import ContestTeam
        from app.utils.enums import TeamApprovalMode

        # Verify contest exists
        contest = await self.repository.get_contest_or_raise(contest_id)

        # Check permissions
        await self.guard.check_create_team(
            user_id=created_by,
            contest=contest,
            member_ids=[created_by]
        )

        # Create team
        team = Team(
            name=team_data.name,
            description=team_data.description,
            created_by=created_by,
            leader_id=created_by,
        )

        # Create team user relationship (creator as member)
        team_user = TeamUser(user_id=created_by)

        # Create contest team relationship
        contest_team = ContestTeam(contest_id=contest_id)

        await self.repository.create_team(
            team=team,
            contest_team=contest_team,
            progress=None,
            team_users=[team_user],
        )

        logger.info(f"Student {created_by} created team {team.id} for contest {contest_id}")

        return StudentTeamCreateAndJoinResponse(
            team_id=team.id,
            team_name=team.name,
            contest_id=contest_id,
            message="Team created successfully",
            approval_status=contest.team_approval_mode,
            you_are_leader=True,
        )

    @cache_delete(
        key_builder=lambda self, contest_id, team_id, user_id: [
            f"student:teams:user:{user_id}:*",
            get_student_team_key(team_id, user_id),
            f"student:contests:{contest_id}:teams:available:*",
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

        Adds student as member to an existing team.
        Approval status depends on team's contest approval mode.

        Implementation:
        - Verifies team exists and belongs to contest
        - Checks if user is already a member
        - Adds TeamUser relationship
        - Returns join status with approval mode

        Args:
            team_id: UUID of team to join
            contest_id: UUID of contest the team belongs to
            user_id: UUID of student joining

        Returns:
            StudentTeamJoinResponse with join status

        Raises:
            TeamNotFoundError: If team not found
            ValueError: If already a member

        Cache Behavior:
            - Invalidates user's team list
            - Invalidates team details
        """
        # Fetch team with members eagerly loaded
        team = await self.repository.get_team_or_raise(team_id)
        team_members_detailed = await self.repository.get_team_members_detailed(team_id)
        
        # Check if user is already a member
        existing_member_ids = {tu.user_id for tu in team_members_detailed}
        if user_id in existing_member_ids:
            raise MemberAlreadyInTeamError(str(user_id), team.name)

        # Add as team member
        await self.repository.add_team_members(
            team_id=team_id,
            member_ids=[user_id],
            leader_id=None,
        )

        logger.info(f"Student {user_id} joined team {team_id} in contest {contest_id}")

        return StudentTeamJoinResponse(
            team_id=team_id,
            contest_id=contest_id,
            message="Successfully joined team",
            status="success",
            approval_status=None,
        )

    @cache_delete(
        key_builder=lambda self, team_id, request, user_id: [
            f"student:teams:user:{user_id}:*",
            get_student_team_key(team_id, user_id),
            f"student:team:{team_id}:members:*",
        ]
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
        Follows exact pattern as TeamService.add_team_members.

        Validation Flow:
        1. Fetch team with eagerly loaded contest relationships
        2. Verify leader authorization
        3. Get all existing team members
        4. Validate team size constraint
        5. Validate all member user IDs exist
        6. Validate no duplicate memberships
        7. Add members via repository
        8. Return updated member list

        Business Rules:
        1. Only team leader can add members
        2. Team must not exceed max_team_size
        3. All user IDs must exist
        4. No user can be added twice
        5. Members cannot already be in team

        Args:
            team_id: UUID of team
            leader_user_id: UUID of leader making request
            member_ids: List of user IDs to add

        Returns:
            StudentTeamAddMemberResponse with updated members

        Raises:
            TeamNotFoundError: If team not found
            PermissionDeniedError: If not team leader
            UserNotFoundError: If user IDs don't exist
            InvalidTeamSizeError: If adding members exceeds team size limit
            MemberAlreadyInTeamError: If any member is already in team

        Cache Behavior:
            - Invalidates team details
            - Invalidates team members list
            - Invalidates user's team list
        """
        # Step 1: Get team with eagerly loaded contests and verify leader
        team = await self.repository.get_team_with_contests_or_raise(team_id)

        if team.leader_id != leader_user_id:
            raise PermissionDeniedError("Only team leader can add members")

        # Get the contest from the team's relationship (now eagerly loaded)
        if not team.team_contests:
            raise ValueError("Team is not registered in any contest")  # This shouldn't happen in normal flow

        contest_team = team.team_contests[0]
        contest = contest_team.contest

        # Step 2: Get existing members count
        existing_team_members = await self.repository.get_all_team_members(team_id)
        current_count = len(existing_team_members)
        new_members_count = len(member_ids)

        # Step 3: Validate team size
        if current_count + new_members_count > contest.max_team_size:
            raise InvalidTeamSizeError(
                size=current_count + new_members_count,
                min_size=1,
                max_size=contest.max_team_size,
            )

        # Step 4: Validate all users exist
        await self.repository.get_users_or_raise(user_ids=member_ids)

        # Step 5: Validate no duplicate memberships
        existing_member_ids = {tu.user_id for tu in existing_team_members}
        already_members = set(member_ids) & existing_member_ids
        if already_members:
            first_duplicate = next(iter(already_members))
            raise MemberAlreadyInTeamError(str(first_duplicate), team.name)

        # Step 6: Add members
        await self.repository.add_team_members(
            team_id=team_id,
            member_ids=member_ids,
            leader_id=None,
        )

        logger.info(
            f"User {leader_user_id} added {len(member_ids)} members to team {team_id}"
        )

        # Step 7: Fetch and return updated members
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

    @cache_delete(
        key_builder=lambda self, team_id, member_id, user_id: [
            f"student:teams:user:{user_id}:*",
            get_student_team_key(team_id, user_id),
            f"student:team:{team_id}:members:*",
        ]
    )
    async def remove_member_from_team(
        self,
        team_id: UUID,
        member_id: UUID,
        user_id: UUID,
    ) -> StudentTeamRemoveMemberResponse:
        """
        Remove a member from a team (leader only).

        Removes a student from a team. Only team leader can remove members.
        Handles leader succession when removing the leader.

        Implementation:
        - Verify user is team leader
        - Remove member via repository
        - Handle leader succession if removing leader
        - Validate minimum team size

        Args:
            team_id: UUID of team
            member_id: UUID of member to remove
            user_id: UUID of leader making request

        Returns:
            StudentTeamRemoveMemberResponse with removal status

        Raises:
            TeamNotFoundError: If team not found
            PermissionDeniedError: If not team leader
            CannotRemoveTeamLeaderError: If removing leader without replacement

        Cache Behavior:
            - Invalidates team details
            - Invalidates team members list
            - Invalidates user's team list
        """
        team = await self.repository.get_team_or_raise(team_id)

        if team.leader_id != user_id:
            raise PermissionDeniedError("Only team leader can remove members")

        # Remove the member
        await self.repository.remove_team_members(
            team_id=team_id,
            member_ids=[member_id],
        )

        logger.info(
            f"User {user_id} removed member {member_id} from team {team_id}"
        )

        return StudentTeamRemoveMemberResponse(
            message="Member removed from team",
            team_id=team_id,
            removed_user_id=member_id,
            status="success",
        )

    @cache_delete(
        key_builder=lambda self, team_id, user_id: [
            f"student:teams:user:{user_id}:*",
            get_student_team_key(team_id, user_id),
        ]
    )
    async def leave_team(
        self, 
        team_id: UUID, 
        user_id: UUID,
    ) -> StudentLeaveTeamResponse:
        """
        Remove student from team (student self-removal).

        Student removing themselves from a team.
        If student is leader, leadership passes to next member.

        Args:
            team_id: UUID of team
            user_id: UUID of student leaving

        Returns:
            StudentLeaveTeamResponse with leave status

        Raises:
            TeamNotFoundError: If team not found
            NotTeamMemberError: If student not in team

        Cache Behavior:
            - Invalidates user's team list
            - Invalidates team details
        """
        team = await self.repository.get_team_or_raise(team_id)

        # Remove student from team
        await self.repository.remove_team_members(
            team_id=team_id,
            member_ids=[user_id],
        )

        logger.info(f"Student {user_id} left team {team_id}")

        return StudentLeaveTeamResponse(
            message="You have left the team",
            team_id=team_id,
            status="success",
        )

    @cache_get(
        key_builder=lambda self, contest_id, user_id, skip=0, limit=10: (
            f"student:contests:{contest_id}:teams:available:user:{user_id}:skip:{skip}:limit:{limit}"
        ),
        ttl=300,
    )
    async def get_available_teams_in_contest(
        self,
        contest_id: UUID,
        user_id: UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> StudentTeamListResponse:
        """
        Get available teams student can join in a contest.

        Retrieves teams in a contest that have open slots.
        Excludes teams student is already a member of.

        Implementation:
        - Retrieves available teams for contest
        - Repository internally fetches contest to get max team size
        - Applies pagination

        Args:
            contest_id: UUID of contest
            user_id: UUID of student
            skip: Pagination skip
            limit: Pagination limit

        Returns:
            StudentTeamListResponse with available teams

        Cache Behavior:
            - Cached per user per contest
            - TTL: 300 seconds
        """
        # Get available teams - repository internally fetches contest for max_team_size
        teams = await self.repository.get_available_teams_in_contest(
            contest_id=contest_id,
            skip=skip,
            limit=limit,
        )

        logger.info(
            f"Student {user_id} viewed available teams in contest {contest_id} (found: {len(teams)})"
        )

        # Build response without pagination object
        team_responses = [
            to_student_team_response(team, team.members, user_id)
            for team in teams
        ]
        
        current_page = (skip // limit) + 1 if limit > 0 else 1
        
        return StudentTeamListResponse(
            teams=team_responses,
            total=len(teams),
            page=current_page,
            page_size=limit,
            has_more=False,  # We don't have total count, so assume no more
        )
