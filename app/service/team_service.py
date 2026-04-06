from typing import cast
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get, cache_set
from app.core.guards.team import TeamOperationGuard
from app.exceptions.team import ApprovalNotAllowedError
from app.mappers.team import (
    apply_team_updates,
    build_create_team_dto,
    build_leader_update_dto,
    build_team_creation_entities,
    build_update_team_dto,
    to_contest_team_response,
    to_contest_team_response_list,
    to_team_member_responses,
)
from app.repositories.dto import PaginationParams, TeamFilters
from app.repositories.team import TeamRepository
from app.schema.team import (
    ContestTeamResponse,
    TeamCreate,
    TeamMemberAdd,
    TeamMemberRemove,
    TeamMemberResponse,
    TeamUpdate,
)
from app.utils.enums import TeamApprovalMode, TeamApprovalStatus, TeamStatus
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
        guard: TeamOperationGuard,
        validator: TeamValidator,
    ):
        self.repository = repository
        self.guard = guard
        self.validator = validator

    @cache_set(
        key_builder=lambda result, **kwargs: get_team_key(result.id), from_result=True
    )
    @cache_delete(
        key_builder=lambda self,
        contest_id,
        *args,
        **kwargs: f"contest:{contest_id}:teams:*"
    )
    async def create_team(
        self, contest_id: UUID, team_data: TeamCreate, created_by: UUID
    ) -> ContestTeamResponse:
        """
        Create a new team in a contest.

        This method creates a team within a specific contest context, performing
        comprehensive validation and permission checks. It validates team name
        uniqueness within the contest, verifies member eligibility, checks team
        size constraints, and ensures the creator has appropriate permissions.

        The method uses a repository pattern for data access and includes
        specialized guards and validator for different aspects of team creation.

        Args:
            contest_id: UUID of the contest where the team will be created
            team_data: TeamCreate schema containing team details including:
                - name: Team name (must be unique within the contest)
                - description: Optional team description
                - logo: Optional team logo URL or path
                - member_ids: List of user UUIDs to include as team members
                - leader_id: Optional UUID of the team leader (must be in member_ids)
                - status: Team status (DRAFT or CONFIRMED)
            created_by: UUID of the user creating the team (requires contest management permission)

        Returns:
            ContestTeamResponse: Response object containing the newly created team
            information including team ID, name, description, logo, status, leader,
            creation details, and timestamps

        Raises:
            ContestNotFoundError: If the specified contest does not exist
            PermissionDeniedError: If the creator lacks permission to manage the contest
            TeamAlreadyExistsError: If a team with the same name already exists in the contest
            InvalidTeamSizeError: If the team size violates contest constraints
            UserNotFoundError: If any specified member or leader does not exist
            InvalidLeaderAssignmentError: If leader_id is specified but not in member_ids

        Cache Behavior:
            - Sets cache entry for the newly created team
            - Invalidates all contest teams cache entries
        """
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_create_team(
            user_id=created_by, contest=contest, member_ids=team_data.member_ids
        )

        existing_team = await self.repository.find_team_by_name(
            contest_id, team_data.name
        )
        self.validator.validate_name_unique(contest_id, team_data.name, existing_team)

        self.validator.validate_team_size(
            len(team_data.member_ids), contest, team_data.status
        )

        await self.repository.get_users_or_raise(team_data.member_ids)

        self.validator.validate_leader_assignment(
            team_data.leader_id, team_data.member_ids, team_data.name
        )

        create_team_data = build_create_team_dto(contest_id, team_data, created_by)
        creator = await self.repository.get_user_or_raise(created_by)
        team, contest_team, progress, team_users = build_team_creation_entities(
            create_team_data,
            contest=contest,
            creator_role=creator.role,
        )

        created_contest_team = await self.repository.create_team(
            team=team,
            contest_team=contest_team,
            progress=progress,
            team_users=team_users,
        )
        return to_contest_team_response(created_contest_team)

    @cache_set(
        key_builder=lambda result, **kwargs: get_team_key(result.id), from_result=True
    )
    @cache_delete(
        key_builder=lambda self, contest_id, *args, **kwargs: [
            f"contest:{contest_id}:teams:*",
            f"contest:{contest_id}:team:*",
        ]
    )
    async def update_team(
        self, contest_id: UUID, team_id: UUID, team_data: TeamUpdate, updated_by: UUID
    ) -> ContestTeamResponse:
        """
        Update an existing team's basic information within a contest.

        This method handles updates to core team metadata including name, description,
        logo, and status. It enforces strict business rules around name uniqueness
        and team size requirements, particularly for status transitions. Team member
        management is intentionally excluded and should be handled through dedicated
        member add/remove endpoints to maintain clear separation of concerns.

        The update process validates all changes against contest rules and existing
        teams, ensuring data integrity and business rule compliance. Status changes
        to CONFIRMED trigger additional validations to ensure the team meets all
        contest requirements.

        Args:
            contest_id: UUID of the contest containing the team
            team_id: UUID of the specific team to update
            team_data: TeamUpdate schema containing optional fields to update:
                - name: New team name (validated for uniqueness within contest)
                - description: Updated team description text
                - logo: New team logo URL or file path
                - status: Team status change (DRAFT or CONFIRMED)
            updated_by: UUID of the user performing the update (must have
                contest management permission)

        Returns:
            ContestTeamResponse: Updated team information including all current
            team data, metadata, timestamps, and status information

        Raises:
            ContestNotFoundError: If the specified contest does not exist
            TeamNotFoundError: If the team is not found within the contest
            PermissionDeniedError: If the user lacks contest management permission
            TeamAlreadyExistsError: If the updated name conflicts with another
                team in the same contest
            InvalidTeamSizeError: If changing status to CONFIRMED but the team
                has fewer than the minimum required members for the contest

        Business Rules:
            - Name uniqueness is enforced within the contest scope
            - Status changes to CONFIRMED require meeting minimum team size
            - Only users with contest management privileges can update teams
            - Member modifications are prohibited through this endpoint
            - All field updates are optional and preserve existing values if not specified

        Cache Behavior:
            - Updates cache entry for the modified team
            - Invalidates contest teams cache and contest-team specific cache entries
            - Ensures consistency across all cached team representations
        """
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_update_team(user_id=updated_by, contest=contest)
        contest_team = await self.repository.get_contest_team_or_raise(
            contest_id, team_id
        )

        team = contest_team.team
        if team_data.name is not None and team_data.name != team.name:
            existing_team = await self.repository.find_team_by_name(
                contest_id, team_data.name
            )
            self.validator.validate_name_unique(
                contest_id, team_data.name, existing_team
            )

        if (
            team_data.status == TeamStatus.CONFIRMED
            and contest_team.team_status == TeamStatus.DRAFT
        ):
            team_member_count = await self.repository.get_team_members_count_or_raise(
                team_id, contest_id
            )

            self.validator.validate_team_size(
                team_member_count, contest, team_data.status
            )
        apply_team_updates(
            team_data=build_update_team_dto(team_id, team_data),
            team=team,
            contest_team=contest_team,
        )
        updated_contest_team = await self.repository.update_team(team, contest_team)
        return to_contest_team_response(updated_contest_team)

    @cache_delete(
        key_builder=lambda self, contest_id, team_id, *args, **kwargs: [
            f"contest:{contest_id}:team:{team_id}:*",
            f"contest:{contest_id}:teams:*",
        ]
    )
    async def approve_team(
        self, contest_id: UUID, team_id: UUID, approved_by: UUID
    ) -> ContestTeamResponse:
        """
        Approve a team in a contest.

        Args:
            contest_id: UUID of the contest containing the team
            team_id: UUID of the team to approve
            approved_by: UUID of the user approving the team

        Returns:
            ContestTeamResponse: Updated team approval state

        Raises:
            ContestNotFoundError: If the contest does not exist
            TeamNotFoundError: If the team is not found in the contest
            PermissionDeniedError: If the user lacks contest management permission
        """
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_update_team(user_id=approved_by, contest=contest)

        contest_team = await self.repository.get_contest_team_or_raise(
            contest_id, team_id
        )

        if contest_team.approval_status == TeamApprovalStatus.APPROVED:
            return to_contest_team_response(contest_team)

        if contest.team_approval_mode == TeamApprovalMode.INSTRUCTOR_REVIEW:
            updated_team = await self.repository.update_team_approval_status(
                contest_team, TeamApprovalStatus.APPROVED
            )
            return to_contest_team_response(updated_team)

        raise ApprovalNotAllowedError(str(team_id), str(contest_id))

    @cache_get(
        key_builder=lambda self,
        contest_id,
        user_id,
        search_term=None,
        status=None,
        skip=0,
        limit=100: f"contest:{contest_id}:teams:user:{user_id}:search:{search_term}:status:{status}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_contest_teams(
        self,
        contest_id: UUID,
        user_id: UUID,
        search_term: str | None = None,
        status: TeamStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, list[ContestTeamResponse]]:
        """
        Retrieve all teams in a contest with optional search and filtering.

        Uses repository pattern for database queries and guard pattern for
        permission validation. Supports pagination, text search by team name,
        and status filtering.

        Implementation:
        - Validates read permissions via TeamOperationGuard
        - Delegates query execution to TeamRepository with filters and pagination
        - Returns paginated results with total count

        Args:
            contest_id: UUID of the contest to get teams from
            user_id: UUID of the user requesting teams (for permission validation)
            search_term: Optional text to search in team names (case-insensitive)
            status: Optional TeamStatus to filter teams (DRAFT or CONFIRMED)
            skip: Number of teams to skip for pagination (default: 0)
            limit: Maximum teams to return, capped at 100 (default: 100)

        Returns:
            Tuple containing:
            - Total count of teams matching the filters
            - List of ContestTeamResponse objects for the requested page

        Raises:
            ContestNotFoundError: If the contest does not exist
            PermissionDeniedError: If user lacks read permission on contest
        """
        # Check permission using guard
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_read_team(user_id=user_id, contest=contest)

        # Create filter and pagination objects
        filters = TeamFilters(search_term=search_term, status=status)
        pagination = PaginationParams(skip=skip, limit=limit)

        # Delegate to repository
        result = await self.repository.get_contest_teams(
            contest_id, filters, pagination
        )

        return result.total, to_contest_team_response_list(result.items)

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
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_read_team(user_id=user_id, contest=contest)

        # Delegate to repository
        contest_team = await self.repository.get_team_by_id(contest_id, team_id)

        return to_contest_team_response(contest_team)

    @cache_delete(
        key_builder=lambda self, contest_id, team_id, *args, **kwargs: [
            f"contest:{contest_id}:team:{team_id}:*",
            f"contest:{contest_id}:teams:*",
            f"team:{team_id}:members:*",
        ]
    )
    async def add_team_members(
        self,
        contest_id: UUID,
        team_id: UUID,
        member_data: TeamMemberAdd,
        updated_by: UUID,
    ) -> tuple[int, list[TeamMemberResponse]]:
        """
        Add members to an existing team in a contest.

        Uses guard pattern for permission validation, validator for business rules,
        and repository pattern for database operations. Performs comprehensive
        validation before adding members.

        Validation Flow:
        1. Validates user has contest management permission (via guard)
        2. Validates all new members are eligible students for contest (via guard)
        3. Validates team exists in contest (via repository)
        4. Validates team size won't exceed maximum after adding members
        5. Validates all new member user IDs exist in database
        6. Validates no duplicate memberships
        7. Validates leader assignment if specified (leader must be existing or new member)

        Implementation:
        - Uses TeamOperationGuard for permission and eligibility checks
        - Uses TeamValidator for business rule validation
        - Delegates database operations to TeamRepository
        - Returns updated member list via get_team_members

        Args:
            contest_id: UUID of the contest containing the team
            team_id: UUID of the team to add members to
            member_data: TeamMemberAdd schema with member IDs and optional leader
            updated_by: UUID of the user performing the action (must have permission)

        Returns:
            TeamMembersResponse with updated member list and team info

        Raises:
            ContestNotFoundError: If the contest does not exist
            TeamNotFoundError: If the team is not found in the contest
            PermissionDeniedError: If user lacks contest management permission
            UserNotFoundError: If any specified member does not exist
            MemberAlreadyInTeamError: If any member is already in the team
            InvalidTeamSizeError: If adding members would exceed team size limit
            InvalidLeaderAssignmentError: If leader is not in combined member list
        """
        # Check permissions and validate members
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_add_team_members(
            user_id=updated_by, contest=contest, member_ids=member_data.member_ids
        )

        contest_team = await self.repository.get_contest_team_or_raise(
            contest_id=contest_id, team_id=team_id
        )

        # Validate team size
        team_members_count = await self.repository.get_team_members_count_or_raise(
            team_id, contest_id
        )
        new_members_count = len(member_data.member_ids)
        self.validator.validate_team_size(
            team_members_count + new_members_count, contest, contest_team.team_status
        )

        # Validate users exist
        await self.repository.get_users_or_raise(user_ids=member_data.member_ids)

        # Validate members are not already in team
        existing_team_members = await self.repository.get_all_team_members(team_id)
        existing_member_ids = {tu.user_id for tu in existing_team_members}
        self.validator.validate_members_not_in_team(
            existing_member_ids, member_data.member_ids, contest_team.team.name
        )
        self.validator.validate_leader_assignment(
            member_data.leader_id,
            list(set(member_data.member_ids) | set(existing_member_ids)),
            contest_team.team.name,
        )
        # Add members using repository
        await self.repository.add_team_members(
            team_id=team_id,
            member_ids=member_data.member_ids,
            leader_id=member_data.leader_id,
        )

        # Return updated member list
        return cast(
            tuple[int, list[TeamMemberResponse]],
            await self.get_team_members(contest_id, team_id, updated_by),
        )

    @cache_delete(
        key_builder=lambda self, contest_id, team_id, *args, **kwargs: [
            f"contest:{contest_id}:team:{team_id}:*",
            f"contest:{contest_id}:teams:*",
            f"team:{team_id}:members:*",
        ]
    )
    async def remove_team_member(
        self,
        contest_id: UUID,
        team_id: UUID,
        member_data: TeamMemberRemove,
        updated_by: UUID,
    ) -> tuple[int, list[TeamMemberResponse]]:
        """
        Remove multiple members from a team in a contest.

        Handles leader succession when removing the current team leader.
        Validates minimum team size requirements for confirmed teams.

        Args:
            contest_id: UUID of the contest containing the team
            team_id: UUID of the team to remove members from
            member_data: TeamMemberRemove schema with member IDs and optional new leader
            updated_by: UUID of the user performing the action (must have permission)

        Returns:
            TeamMembersResponse with updated member list and team info

        Raises:
            ContestNotFoundError: If the contest does not exist
            TeamNotFoundError: If the team is not found in the contest
            PermissionDeniedError: If user lacks team management permission
            MemberNotInTeamError: If any member is not in the team
            CannotRemoveTeamLeaderError: If removing leader without replacement
            InvalidLeaderAssignmentError: If new leader is being removed
            InvalidTeamSizeError: If removal would violate minimum team size
        """
        # Check permission and get team
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_remove_team_members(user_id=updated_by, contest=contest)
        team = await self.repository.get_team_or_raise(team_id, contest_id)
        contest_team = await self.repository.get_contest_team_or_raise(
            contest_id, team_id
        )
        team_members = await self.repository.get_all_team_members(team_id=team_id)
        team_member_ids = {tm.user_id for tm in team_members}
        self.validator.validate_members_in_team(
            team_member_ids, set(member_data.member_ids), team.name
        )
        un_removed_ids: set = set(team_member_ids) - set(member_data.member_ids)
        self.validator.validate_team_size(
            len(un_removed_ids), contest, contest_team.team_status
        )
        self.validator.validate_leader_change(
            member_data.member_ids,
            member_data.new_leader_id,
            team.leader_id,
            team.name,
        )
        # Remove members using repository
        await self.repository.remove_team_members(
            team_id=team_id, member_ids=member_data.member_ids
        )

        # Update team leader (always call to handle leader changes)
        update_data = build_leader_update_dto(team_id, member_data.new_leader_id)
        apply_team_updates(team_data=update_data, team=team, contest_team=contest_team)
        await self.repository.update_team(team, contest_team)
        return cast(
            tuple[int, list[TeamMemberResponse]],
            await self.get_team_members(contest_id, team_id, updated_by),
        )

    @cache_get(
        key_builder=lambda self,
        contest_id,
        team_id,
        user_id,
        search_term=None,
        skip=0,
        limit=100: f"team:{team_id}:members:user:{user_id}:search:{search_term}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_team_members(
        self,
        contest_id: UUID,
        team_id: UUID,
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
        - Delegates paginated query to TeamRepository with search support
        - Returns formatted response with member list and team info

        Args:
            contest_id: UUID of the contest containing the team
            team_id: UUID of the team to get members from
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
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_read_team(user_id=user_id, contest=contest)

        contest_team = await self.repository.get_contest_team_or_raise(
            contest_id, team_id
        )
        team = contest_team.team

        # Delegate to repository for paginated member retrieval
        total, results = await self.repository.get_team_members_paginated(
            team_id=team_id, search_term=search_term, skip=skip, limit=limit
        )

        # Transform to response objects
        users = [user for user, _ in results]
        members = to_team_member_responses(users, team=team)

        return total, members
