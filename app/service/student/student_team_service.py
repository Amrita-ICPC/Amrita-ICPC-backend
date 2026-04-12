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
    - Leave teams
    - Transform repository data to API response schemas
    - Coordinate cache invalidation for team-related data
"""

from typing import TYPE_CHECKING
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get, cache_set
from app.core.logger import logger
from app.exceptions.team import TeamNotFoundError
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
    StudentTeamCreateAndJoinResponse,
    StudentTeamCreateRequest,
    StudentTeamJoinResponse,
    StudentTeamListResponse,
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
        key_builder=lambda self, user_id, skip=0, limit=10: f"student:teams:user:{user_id}:skip:{skip}:limit:{limit}",
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
        return to_student_teams_list_response(result.items, result.total, user_id)

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

        # Check if current user is member/leader
        is_current_user_member = any(member.id == user_id for member in members)
        is_current_user_leader = team.leader_id == user_id

        logger.info(f"Student {user_id} viewed team {team_id} details")
        return to_student_team_response(
            team, members, is_current_user_member, is_current_user_leader, user_id
        )

    @cache_get(
        key_builder=lambda self, contest_id, user_id, skip=0, limit=10: f"student:contest:{contest_id}:teams:available:user:{user_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_available_teams_in_contest(
        self,
        contest_id: UUID,
        user_id: UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> list["StudentTeamResponse"]:
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
            List of StudentTeamAvailableResponse objects

        Raises:
            ContestNotFoundError: If contest not found

        Cache Behavior:
            - Cached per contest per student
            - TTL: 300 seconds
        """
        contest = await self.repository.get_contest_or_raise(contest_id)

        result = await self.repository.get_available_teams_in_contest(
            contest_id=contest_id,
            max_size=contest.max_team_size,
            skip=skip,
            limit=limit,
        )

        logger.info(
            f"Student {user_id} queried available teams in contest {contest_id} (found: {len(result)})"
        )
        return to_student_available_teams_list_response(result, contest_id)

    @cache_delete(
        key_builder=lambda self, contest_id, user_id: [
            f"student:teams:user:{user_id}:*",
            f"student:contest:{contest_id}:teams:available:user:{user_id}:*",
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

        Approval Status:
        - AUTO_APPROVE: Team approved automatically
        - INSTRUCTOR_REVIEW: Team waiting for instructor approval

        Process:
        1. Validate contest exists and not soft-deleted
        2. Create team with student as creator and leader
        3. Create ContestTeam record with contest
        4. Create ContestTeamProgress for tracking
        5. Return response with team and approval status

        Implementation:
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
            TeamAlreadyExistsError: If team name conflicts in contest
            PermissionDeniedError: If user not eligible to create teams

        Cache Behavior:
            - Invalidates student's teams list
            - Invalidates available teams in contest
        """
        contest = await self.repository.get_contest_or_raise(contest_id)

        if contest.is_deleted:
            raise TeamNotFoundError(str(contest_id), str(contest_id))

        # Create team and register in contest
        team, contest_team, progress = await self.repository.create_student_team_for_contest(
            team_name=team_data.name,
            team_description=team_data.description,
            contest_id=contest_id,
            created_by=created_by,
        )

        logger.info(
            f"Student {created_by} created team '{team.name}' and registered for contest {contest_id}"
        )

        return to_student_team_create_and_join_response(
            team, contest_team, created_by
        )

    @cache_delete(
        key_builder=lambda self, team_id, user_id: [
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

        contest = await self.repository.get_contest_or_raise(contest_id)

        # Add student to team (validates size and membership)
        team_user = await self.repository.add_student_to_team(
            team_id=team_id, user_id=user_id, contest_id=contest_id
        )

        logger.info(f"Student {user_id} joined team {team_id} in contest {contest_id}")

        return to_student_team_join_response(team, contest, team_user)

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
        team_user = await self.repository.get_team_user_or_raise(team_id, user_id)

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
