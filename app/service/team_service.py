from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.core.cache.decorators import cache_delete, cache_get, cache_set
from app.core.guards.team import TeamOperationGuard
from app.core.permissions import ContestPermission, TeamPermission
from app.exceptions.contest import ContestNotFoundError
from app.exceptions.team import (
    InvalidLeaderAssignmentError,
    InvalidTeamSizeError,
    MemberAlreadyInTeamError,
    MemberNotInTeamError,
    TeamNotFoundError,
)
from app.exceptions.user import UserNotFoundError
from app.models.contest import (
    Contest,
    ContestTeam,
)
from app.models.team import Team, TeamUser
from app.models.user import User
from app.repositories.team import CreateTeamData, TeamRepository, UpdateTeamData
from app.schema.team import (
    ContestTeamResponse,
    TeamCreate,
    TeamMemberAdd,
    TeamMemberRemove,
    TeamMemberResponse,
    TeamMembersResponse,
    TeamUpdate,
)
from app.utils.enums import TeamStatus
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
    """
    Service layer for team management operations.

    Handles all team-related business logic including creation, updates,
    retrieval, and validation. Manages relationships between teams, contests,
    and users while enforcing business rules and permissions.

    Features:
    - Team creation with member validation and permission checks
    - Team updates with conflict detection and size validation
    - Team retrieval with search, filtering, and pagination
    - Cache management for performance optimization
    - Permission enforcement at the service level
    """

    def __init__(
        self,
        db: Session,
        repository: TeamRepository,
        guard: TeamOperationGuard,
        validator: TeamValidator,
    ):
        self.db = db
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
        contest = self.repository.get_contest_or_raise(contest_id)
        self.guard.check_create_team(
            user_id=created_by, contest=contest, member_ids=team_data.member_ids
        )

        existing_team = self.repository.find_team_by_name(contest_id, team_data.name)
        self.validator.validate_name_unique(contest_id, team_data.name, existing_team)

        self.validator.validate_team_size(
            len(team_data.member_ids), contest, team_data.status
        )

        self.repository.get_users_or_raise(team_data.member_ids)

        self.validator.validate_leader_assignment(
            team_data.leader_id, team_data.member_ids
        )

        # Convert DTO to repository data object
        create_team_data = CreateTeamData(
            contest_id=contest_id,
            created_by=created_by,
            name=team_data.name,
            description=team_data.description,
            logo=team_data.logo,
            leader_id=team_data.leader_id,
            member_ids=team_data.member_ids,
            status=team_data.status,
        )

        contest_team = self.repository.create_team(create_team_data)
        return ContestTeamResponse.from_contest_team(contest_team)

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
        contest = self.repository.get_contest_or_raise(contest_id)
        self.guard.check_update_team(user_id=updated_by, contest=contest)
        contest_team = self.repository.get_contest_team_or_raise(contest_id, team_id)

        team = contest_team.team
        if team_data.name is not None and team_data.name != team.name:
            existing_team = self.repository.find_team_by_name(
                contest_id, team_data.name
            )
            self.validator.validate_name_unique(
                contest_id, team_data.name, existing_team
            )

        if (
            team_data.status == TeamStatus.CONFIRMED
            and contest_team.team_status == TeamStatus.DRAFT
        ):
            team_meber_count = self.repository.get_team_members_count_or_raise(team_id)

            self.validator.validate_team_size(
                team_meber_count, contest, team_data.status
            )
        updated_contest_team = self.repository.update_team(
            UpdateTeamData(
                team_id=team_id,
                name=team_data.name,
                description=team_data.description,
                logo=team_data.logo,
                status=team_data.status,
            ),
            team,
            contest_team,
        )
        return ContestTeamResponse.from_contest_team(updated_contest_team)

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

        Supports pagination, text search by team name, and status filtering.
        Automatically enforces read permissions on the contest.

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
        # Check permission
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_read_contest(self.db, user_id=user_id, contest=contest)

        # Execute the query
        base_query = (
            self.db.query(ContestTeam)
            .options(joinedload(ContestTeam.team))
            .join(Team, ContestTeam.team_id == Team.id)
            .filter(ContestTeam.contest_id == contest_id)
        )

        if search_term:
            base_query = base_query.filter(Team.name.ilike(f"%{search_term}%"))

        if status:
            base_query = base_query.filter(ContestTeam.team_status == status)

        total = base_query.count()
        contest_teams = base_query.offset(skip).limit(limit).all()

        return total, [
            ContestTeamResponse.from_contest_team(ct) for ct in contest_teams
        ]

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

        Enforces read permissions on the contest before returning team data.
        Used for getting detailed information about a single team.

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
        # Check permission
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_read_contest(self.db, user_id=user_id, contest=contest)

        # Get the team
        contest_team = (
            self.db.query(ContestTeam)
            .filter(
                ContestTeam.contest_id == contest_id, ContestTeam.team_id == team_id
            )
            .first()
        )

        if not contest_team:
            raise TeamNotFoundError(str(team_id), str(contest_id))

        return ContestTeamResponse.from_contest_team(contest_team)

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
    ) -> TeamMembersResponse:
        """
        Add members to an existing team in a contest.

        Validates member eligibility, team size constraints, and handles
        leader assignment if specified. Prevents duplicate memberships.

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
            PermissionDeniedError: If user lacks team management permission
            UserNotFoundError: If any specified member does not exist
            MemberAlreadyInTeamError: If member is already in the team
            InvalidTeamSizeError: If adding members would exceed team size limit
        """
        # Check contest and get team
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_manage_contest(
            self.db, user_id=updated_by, contest=contest
        )

        contest_team = (
            self.db.query(ContestTeam)
            .filter(
                ContestTeam.contest_id == contest_id, ContestTeam.team_id == team_id
            )
            .first()
        )

        if not contest_team:
            raise TeamNotFoundError(str(team_id), str(contest_id))

        team = contest_team.team

        # Get current team member count
        existing_members = (
            self.db.query(TeamUser).filter(TeamUser.team_id == team_id).all()
        )
        existing_member_ids = {tu.user_id for tu in existing_members}

        current_member_count = len(existing_members)

        # Check if adding new members would exceed team size
        new_member_count = len(member_data.member_ids)
        if current_member_count + new_member_count > contest.max_team_size:
            raise InvalidTeamSizeError(
                current_member_count + new_member_count,
                contest.min_team_size,
                contest.max_team_size,
            )

        # Validate members existence and not already in team
        users = self.db.query(User).filter(User.id.in_(member_data.member_ids)).all()
        found_ids = {u.id for u in users}
        missing = set(member_data.member_ids) - found_ids
        if missing:
            raise UserNotFoundError(str(next(iter(missing))))

        for user in users:
            if user.id in existing_member_ids:
                raise MemberAlreadyInTeamError(str(user.id), team.name)

        TeamPermission.is_student_allowed_for_contest(
            self.db, user_ids=member_data.member_ids, contest_id=contest_id
        )

        # Add new members
        for member_id in member_data.member_ids:
            team_user = TeamUser(team_id=team_id, user_id=member_id)
            self.db.add(team_user)

        # Update leader if specified
        if member_data.leader_id:
            team.leader_id = member_data.leader_id

        self.db.flush()
        self.db.refresh(team)

        # Return updated member list
        return await self.get_team_members(contest_id, team_id, updated_by)

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
    ) -> TeamMembersResponse:
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
        # Check contest and get team
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_manage_contest(
            self.db, user_id=updated_by, contest=contest
        )

        contest_team = (
            self.db.query(ContestTeam)
            .filter(
                ContestTeam.contest_id == contest_id, ContestTeam.team_id == team_id
            )
            .first()
        )

        if not contest_team:
            raise TeamNotFoundError(str(team_id), str(contest_id))

        team = contest_team.team

        # Get current team members to validate
        current_team_users = {
            tu.user_id: tu
            for tu in self.db.query(TeamUser).filter(TeamUser.team_id == team_id).all()
        }

        current_member_count = len(current_team_users)
        members_to_remove = len(member_data.member_ids)

        # Validate all members are in team
        for member_id in member_data.member_ids:
            if member_id not in current_team_users:
                raise MemberNotInTeamError(str(member_id), team.name)

        # Check if removing leader
        is_removing_leader = team.leader_id in member_data.member_ids

        # Check minimum team size for confirmed teams
        if (
            contest_team.team_status == TeamStatus.CONFIRMED
            and current_member_count - members_to_remove < contest.min_team_size
        ):
            raise InvalidTeamSizeError(
                current_member_count - members_to_remove,
                contest.min_team_size,
                contest.max_team_size,
            )

        # Validate new leader if specified
        if member_data.new_leader_id:
            if member_data.new_leader_id in member_data.member_ids:
                raise InvalidLeaderAssignmentError(
                    str(member_data.new_leader_id), team.name
                )
            if member_data.new_leader_id not in current_team_users:
                raise MemberNotInTeamError(str(member_data.new_leader_id), team.name)

        # Remove all specified members
        for member_id in member_data.member_ids:
            team_user = current_team_users[member_id]
            self.db.delete(team_user)

        # Update leader if needed
        if is_removing_leader:
            if member_data.new_leader_id:
                team.leader_id = member_data.new_leader_id
            else:
                # Auto Assign new leader if current leader is removed and no new leader specified
                remaining_members = [
                    tu
                    for tu in current_team_users.values()
                    if tu.user_id not in member_data.member_ids
                ]
                team.leader_id = (
                    remaining_members[0].user_id if remaining_members else None
                )

        self.db.flush()
        self.db.refresh(team)

        # Return updated member list
        return await self.get_team_members(contest_id, team_id, updated_by)

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
    ) -> TeamMembersResponse:
        """
        Retrieve all members of a team with optional search and pagination.

        Supports text search by member name or email and includes team context
        information in the response.

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
        # Check contest permission
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_read_contest(self.db, user_id=user_id, contest=contest)

        # Check team exists
        contest_team = (
            self.db.query(ContestTeam)
            .filter(
                ContestTeam.contest_id == contest_id, ContestTeam.team_id == team_id
            )
            .first()
        )

        if not contest_team:
            raise TeamNotFoundError(str(team_id), str(contest_id))

        team = contest_team.team

        # Build query for team members
        base_query = (
            self.db.query(User, TeamUser)
            .join(TeamUser, User.id == TeamUser.user_id)
            .filter(TeamUser.team_id == team_id)
        )

        # Apply search filter if provided
        if search_term:
            search_pattern = f"%{search_term}%"
            base_query = base_query.filter(
                (User.name.ilike(search_pattern)) | (User.email.ilike(search_pattern))
            )

        # Get total count
        total = base_query.count()

        # Get paginated results
        results = base_query.offset(skip).limit(limit).all()

        # Transform to response objects
        members = []
        for user, _ in results:
            member = TeamMemberResponse(
                id=user.id,
                user_id=user.user_id,
                name=user.name,
                email=user.email,
                role=user.role.value,
                is_leader=(team.leader_id == user.id),
            )
            members.append(member)

        return TeamMembersResponse(
            total=total,
            members=members,
        )
