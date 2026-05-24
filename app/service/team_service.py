from app.repositories.contest import ContestRepository
from app.repositories.user import UserRepository
from typing import Optional
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get
from app.core.guards.team import TeamOperationGuard
from app.exceptions.team import ApprovalNotAllowedError
from app.mappers.team import (
    to_contest_team_member_responses,
    to_contest_team_response,
    to_team_list_response,
    to_team_member_responses,
)
from app.repositories.dto import PaginationParams, TeamFilters
from app.repositories.student.contest_team import ContestTeamRepository
from app.repositories.team import TeamRepository
from app.schema.team import (
    ContestTeamResponse,
    TeamListResponse,
    TeamMemberAdd,
    TeamMemberRemove,
    TeamMemberResponse,
)
from app.utils.enums import (
    ContestTeamMemberStatus,
    TeamApprovalMode,
    TeamApprovalStatus,
    TeamStatus,
)
from app.validators.team import TeamValidator


def get_team_key(team_id: UUID) -> str:
    """
    Generate a cache key for a team.

    Args:
        team_id: UUID of the team

    Returns:
        Formatted cache key string for the team
    """
    return f"team:{team_id}"


class TeamService:
    """Service layer for team management operations.

    This service orchestrates team-related business logic by coordinating between
    the repository layer (data access), guard layer (permissions), and validator
    layer (business rules). It implements a clean architecture pattern with clear
    separation of concerns.

    Architecture:
        - Repository Pattern: All database operations delegated to TeamRepository
        - Guard Pattern: Permission checks centralized in TeamOperationGuard
        - Validator Pattern: Business rule validation in TeamValidator
        - No direct database access: Service layer remains database-agnostic

    Key Responsibilities:
        - Orchestrate team CRUD operations (create, read, update, delete)
        - Manage team membership (add/remove members, update leader)
        - Enforce permission checks before operations
        - Validate business rules (team size, member eligibility, etc.)
        - Transform repository data to API response schemas
        - Coordinate cache invalidation for team-related data

    Dependencies:
        - TeamRepository: Handles all database queries and mutations
        - TeamOperationGuard: Validates user permissions for operations
        - TeamValidator: Enforces business rules and constraints

    Cache Strategy:
        - Team data cached with TTL of 300 seconds
        - Cache keys include user_id for permission-aware caching
        - Cache invalidated on team mutations (create, update, delete)
    """

    def __init__(
        self,
        repository: TeamRepository,
        contest_team_repository: ContestTeamRepository,
        contest_repository: ContestRepository,
        guard: TeamOperationGuard,
        validator: TeamValidator,
    ):
        self.guard = guard
        self.repository = repository
        self.validator = validator
        self.contest_repository = contest_repository
        self.contest_team_repository = contest_team_repository

    @cache_delete(
        key_builder=lambda self, contest_id, contest_team_id, approved_by: [
            f"contest:{contest_id}:team:{contest_team_id}:*",
            f"contest:{contest_id}:teams:*",
        ]
    )
    async def approve_team(
        self, contest_id: UUID, contest_team_id: UUID, approved_by: UUID
    ) -> ContestTeamResponse:
        """
        Approve a team in a contest.

        Args:
            contest_id: UUID of the contest containing the team
            contest_team_id: UUID of the contest team to approve
            approved_by: UUID of the user approving the team

        Returns:
            ContestTeamResponse: Updated team approval state

        Raises:
            ContestNotFoundError: If the contest does not exist
            ContestTeamNotFoundException: If the contest team is not found in the contest
            PermissionDeniedError: If the user lacks contest management permission
            ApprovalNotAllowedError: If the user is not allowed to approve this team
        """
        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        await self.guard.check_update_team(user_id=approved_by, contest=contest)

        contest_team = await self.contest_team_repository.get_contest_team_by_id_or_raise(
            contest_team_id
        )

        if contest_team.approval_status != TeamApprovalStatus.APPROVED:
            if contest.team_approval_mode == TeamApprovalMode.INSTRUCTOR_REVIEW:
                contest_team.approval_status = TeamApprovalStatus.APPROVED
                contest_team = await self.contest_team_repository.update_contest_team(
                    contest_team
                )
            else:
                raise ApprovalNotAllowedError(str(contest_team_id), str(contest_id))

        # Fetch unique accepted members for response
        members = await self.contest_team_repository.get_contest_team_members(
            contest_team_id=contest_team.id,
            contestTeamMemberStatus=[ContestTeamMemberStatus.ACCEPTED],
        )
        seen_users = set()
        unique_members = []
        for m in members:
            if m.user_id not in seen_users:
                seen_users.add(m.user_id)
                unique_members.append(m)

        return to_contest_team_response(contest_team, members=unique_members)

    @cache_delete(
        key_builder=lambda self, contest_id, contest_team_id, rejected_by: [
            f"contest:{contest_id}:team:{contest_team_id}:*",
            f"contest:{contest_id}:teams:*",
        ]
    )
    async def reject_team(
        self, contest_id: UUID, contest_team_id: UUID, rejected_by: UUID
    ) -> ContestTeamResponse:
        """
        Reject a team in a contest.

        Args:
            contest_id: UUID of the contest containing the team
            contest_team_id: UUID of the contest team to reject
            rejected_by: UUID of the user rejecting the team

        Returns:
            ContestTeamResponse: Updated team approval state
        """
        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        await self.guard.check_update_team(user_id=rejected_by, contest=contest)

        contest_team = await self.contest_team_repository.get_contest_team_by_id_or_raise(
            contest_team_id
        )

        if contest.team_approval_mode != TeamApprovalMode.INSTRUCTOR_REVIEW:
            raise ApprovalNotAllowedError(str(contest_team_id), str(contest_id))

        if contest_team.approval_status != TeamApprovalStatus.REJECTED:
            contest_team.approval_status = TeamApprovalStatus.REJECTED
            contest_team = await self.contest_team_repository.update_contest_team(
                contest_team
            )

        # Fetch unique accepted members for response
        members = await self.contest_team_repository.get_contest_team_members(
            contest_team_id=contest_team.id,
            contestTeamMemberStatus=[ContestTeamMemberStatus.ACCEPTED],
        )
        seen_users = set()
        unique_members = []
        for m in members:
            if m.user_id not in seen_users:
                seen_users.add(m.user_id)
                unique_members.append(m)

        return to_contest_team_response(contest_team, members=unique_members)

    @cache_delete(
        key_builder=lambda self, contest_id, contest_team_id, disqualified_by: [
            f"contest:{contest_id}:team:{contest_team_id}:*",
            f"contest:{contest_id}:teams:*",
        ]
    )
    async def disqualify_team(
        self, contest_id: UUID, contest_team_id: UUID, disqualified_by: UUID
    ) -> ContestTeamResponse:
        """
        Disqualify a team from a contest.

        Args:
            contest_id: UUID of the contest containing the team
            contest_team_id: UUID of the contest team to disqualify
            disqualified_by: UUID of the user disqualifying the team

        Returns:
            ContestTeamResponse: Updated team status
        """
        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        await self.guard.check_update_team(user_id=disqualified_by, contest=contest)

        contest_team = await self.contest_team_repository.get_contest_team_by_id_or_raise(
            contest_team_id
        )

        if contest_team.team_status != TeamStatus.DISQUALIFIED:
            contest_team.team_status = TeamStatus.DISQUALIFIED
            contest_team = await self.contest_team_repository.update_contest_team(
                contest_team
            )

        # Fetch unique accepted members for response
        members = await self.contest_team_repository.get_contest_team_members(
            contest_team_id=contest_team.id,
            contestTeamMemberStatus=[ContestTeamMemberStatus.ACCEPTED],
        )
        seen_users = set()
        unique_members = []
        for m in members:
            if m.user_id not in seen_users:
                seen_users.add(m.user_id)
                unique_members.append(m)

        return to_contest_team_response(contest_team, members=unique_members)

    @cache_get(
        key_builder=lambda self,
        contest_id,
        user_id,
        search_term=None,
        status=None,
        approval_status=None,
        skip=0,
        limit=100: f"contest:{contest_id}:teams:user:{user_id}:search:{search_term}:status:{status}:approval:{approval_status}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_contest_teams(
        self,
        contest_id: UUID,
        user_id: UUID,
        search_term: str | None = None,
        status: TeamStatus | None = None,
        approval_status: TeamApprovalStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> TeamListResponse:
        """
        Retrieve all teams in a contest with optional search and filtering.

        Uses repository pattern for database queries and guard pattern for
        permission validation. Supports pagination, text search by team name,
        and status filtering (team status and approval status).

        Implementation:
        - Validates read permissions via TeamOperationGuard
        - Delegates query execution to TeamRepository with filters and pagination
        - Fetches team status counts
        - Returns TeamListResponse with paginated results and counts

        Args:
            contest_id: UUID of the contest to get teams from
            user_id: UUID of the user requesting teams (for permission validation)
            search_term: Optional text to search in team names (case-insensitive)
            status: Optional TeamStatus to filter teams (DRAFT, CONFIRMED, DISQUALIFIED)
            approval_status: Optional TeamApprovalStatus to filter teams (WAITING, APPROVED, REJECTED)
            skip: Number of teams to skip for pagination (default: 0)
            limit: Maximum teams to return, capped at 100 (default: 100)

        Returns:
            TeamListResponse: Paginated results and status counts

        Raises:
            ContestNotFoundError: If the contest does not exist
            PermissionDeniedError: If user lacks read permission on contest
        """
        # Check permission using guard
        contest = await self.contest_repository.get_contest_or_raise(contest_id)

        await self.guard.check_read_team(user_id=user_id, contest=contest)

        status_filter = [status] if status is not None else [TeamStatus.DISQUALIFIED, TeamStatus.CONFIRMED]
        filters = TeamFilters(
            search_term=search_term, status=status_filter, approval_status=approval_status
        )
        pagination = PaginationParams(skip=skip, limit=limit)

        # Delegate to repository
        result = await self.contest_team_repository.get_contest_teams(
            contest_id, filters, pagination
        )

        team_members_map = {}
        for team in result.items:
            members = await self.contest_team_repository.get_contest_team_members(
                contest_team_id=team.id,
                contestTeamMemberStatus=[ContestTeamMemberStatus.ACCEPTED],
            )
            # Ensure uniqueness by user_id
            seen_users = set()
            unique_members = []
            for m in members:
                if m.user_id not in seen_users:
                    seen_users.add(m.user_id)
                    unique_members.append(m)
            team_members_map[team.id] = unique_members

        # Get status counts
        status_counts = await self.contest_team_repository.count_teams_by_status(contest_id)

        return to_team_list_response(
            result.total, result.items, status_counts, team_members_map
        )

    @cache_get(
        key_builder=lambda self,
        contest_id,
        team_id,
        user_id: f"contest:{contest_id}:team:{team_id}:user:{user_id}",
        ttl=300,
    )
    async def get_team_by_id(
        self, contest_id: UUID, team_id: UUID, user_id: UUID
    ) -> ContestTeamResponse:
        """
        Retrieve a specific team by its ID within a contest.

        Uses guard pattern for permission validation and repository pattern
        for database queries. Enforces read permissions before returning team data.

        Implementation:
        - Validates contest exists via TeamRepository
        - Validates read permissions via TeamOperationGuard
        - Retrieves team data via TeamRepository with eager loading
        - Returns formatted response with team details

        Args:
            contest_id: UUID of the contest where the team is registered
            team_id: UUID of the team to retrieve
            user_id: UUID of the user requesting team data (for permission validation)

        Returns:
            ContestTeamResponse containing detailed team information

        Raises:
            ContestNotFoundError: If the contest does not exist
            TeamNotFoundError: If the team is not found in the contest
            PermissionDeniedError: If user lacks read permission on contest
        """
        # Check permission using guard
        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        await self.guard.check_read_team(user_id=user_id, contest=contest)

        # Delegate to repository
        contest_team = await self.repository.get_team_by_id(contest_id, team_id)
       

        return to_contest_team_response(contest_team)


    @cache_get(
        key_builder=lambda self,
        contest_id,
        contest_team_id,
        user_id,
        search_term=None,
        skip=0,
        limit=100: f"team:{contest_team_id}:members:user:{user_id}:search:{search_term}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_team_members(
        self,
        contest_id: UUID,
        contest_team_id: UUID,
        user_id: UUID,
        search_term: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, list[TeamMemberResponse]]:
        """
        Retrieve all members of a team with optional search and pagination.

        Uses guard pattern for permission validation and repository pattern
        for database queries. Supports text search by member name or email.

        Implementation:
        - Validates contest exists via TeamRepository
        - Validates read permissions via TeamOperationGuard
        - Delegates paginated query to ContestTeamRepository with search support
        - Returns formatted response with member list and team info

        Args:
            contest_id: UUID of the contest containing the team
            contest_team_id: UUID of the contest team to get members from
            user_id: UUID of the user requesting members (for permission validation)
            search_term: Optional text to search in member names or emails
            skip: Number of members to skip for pagination (default: 0)
            limit: Maximum members to return, capped at 100 (default: 100)

        Returns:
            TeamMembersResponse with member list, total count, and team info

        Raises:
            ContestNotFoundError: If the contest does not exist
            TeamNotFoundError: If the team is not found in the contest
            PermissionDeniedError: If user lacks read permission on contest
        """
        # Check permission and get team
        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        await self.guard.check_read_team(user_id=user_id, contest=contest)

        contest_team = await self.contest_team_repository.get_contest_team_by_id_or_raise(
            contest_team_id
        )

        pagination = PaginationParams(skip=skip, limit=limit)
        paginated_result = await self.contest_team_repository.get_contest_team_members_paginated(
            contest_team_id=contest_team_id,
            pagination=pagination,
            status=[ContestTeamMemberStatus.ACCEPTED],
            search_term=search_term,
        )

        # Transform to response objects
        members = to_contest_team_member_responses(
            paginated_result.items,
            leader_id=contest_team.leader_id,
        )

        return paginated_result.total, members
