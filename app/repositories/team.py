from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.exceptions.contest import ContestNotFoundError
from app.exceptions.team import TeamNotFoundError
from app.exceptions.user import UserNotFoundError
from app.models.contest import Contest, ContestTeam, ContestTeamProgress
from app.models.team import Team, TeamUser
from app.models.user import User
from app.repositories.dto import (
    PaginatedResult,
    PaginationParams,
    TeamFilters,
)
from app.utils.enums import TeamApprovalStatus, TeamStatus


class TeamRepository:
    """Repository for team-related database operations.

    This class implements the Repository Pattern, providing a clean abstraction
    over database operations for team management. It encapsulates all SQL queries
    and ORM interactions, keeping the service layer database-agnostic.

    Responsibilities:
        - Execute all database queries for teams, contests, and users
        - Handle ORM relationships and eager loading optimizations
        - Provide type-safe data access methods
        - Raise domain-specific exceptions (not database exceptions)
        - Return domain objects and DTOs (not raw query results)

    Design Principles:
        - Single Responsibility: Only handles data access
        - Encapsulation: Hides SQLAlchemy implementation details
        - Fail Fast: Raises exceptions immediately on data not found
        - Type Safety: Uses DTOs for data transfer

    Key Methods:
        - Contest Operations: get_contest_or_raise, get_contest_teams
        - Team Operations: create_team, update_team, get_team_by_id
        - Member Operations: add_team_members, remove_team_members, get_team_members_paginated
        - Validation Helpers: get_users_or_raise, find_team_by_name

    Exception Strategy:
        - Raises domain exceptions (TeamNotFoundError, ContestNotFoundError, etc.)
        - Never exposes SQLAlchemy exceptions to callers
        - Provides clear error messages with entity IDs
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # contest team related operations
    async def get_contest_or_raise(self, contest_id: UUID) -> Contest:
        """
        Retrieve a contest by its ID or raise an exception if not found.

        Args:
            contest_id: ID of the contest to retrieve.
        Returns:
            The Contest object if found.
        Raises:
            ContestNotFoundError: If the contest with the given ID does not exist.
        """
        result = await self.db.execute(select(Contest).filter(Contest.id == contest_id))
        contest = result.scalars().first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))
        return contest

    async def get_user_or_raise(self, user_id: UUID) -> User:
        """
        Retrieve a user by their ID or raise an exception if not found.

        Args:
            user_id: ID of the user to retrieve.
        Returns:
            The User object if found.
        Raises:
            UserNotFoundError: If the user with the given ID does not exist.
        """
        result = await self.db.execute(select(User).filter(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise UserNotFoundError(str(user_id))
        return user

    async def get_users_or_raise(self, user_ids: list[UUID]) -> list[User]:
        """
        Retrieve multiple users by their IDs or raise an exception if any are not found.

        Args:
            user_ids: List of user IDs to retrieve.
        Returns:
            List of User objects corresponding to the provided IDs.
        Raises:
            UserNotFoundError: If any user with the given IDs does not exist.
        """
        unique_ids = set(user_ids)
        result = await self.db.execute(select(User).filter(User.id.in_(unique_ids)))
        users = list(result.scalars().all())
        if len(users) != len(user_ids):
            found_user_ids = {user.id for user in users}
            missing_user_ids = unique_ids - found_user_ids
            raise UserNotFoundError(str(next(iter(missing_user_ids))))
        return users

    async def find_team_by_name(self, contest_id: UUID, team_name: str) -> Team | None:
        """
        Find a team by its name within a specific contest.

        Args:
            contest_id: ID of the contest to search within.
            team_name: Name of the team to find.

        Returns:
            The Team object if found, otherwise None.
        """
        result = await self.db.execute(
            select(Team)
            .join(ContestTeam)
            .filter(
                ContestTeam.contest_id == contest_id,
                Team.name == team_name,
            )
        )
        return result.scalars().first()

    async def get_team_or_raise(
        self, team_id: UUID, contest_id: UUID | None = None
    ) -> Team:
        """
        Retrieve a team by its ID or raise an exception if not found.

        Args:
            team_id: ID of the team to retrieve.
            contest_id: Optional ID of the contest for context in error messages.
        Returns:
            The Team object if found.
        Raises:
            TeamNotFoundError: If the team with the given ID does not exist.
        """
        result = await self.db.execute(select(Team).filter(Team.id == team_id))
        team = result.scalars().first()
        if not team:
            raise TeamNotFoundError(
                str(team_id), str(contest_id) if contest_id else "unknown"
            )
        return team

    async def get_team_with_contests_or_raise(
        self, team_id: UUID, contest_id: UUID | None = None
    ) -> Team:
        """
        Retrieve a team with eagerly loaded contest relationships.

        Eagerly loads all relationships needed to access nested data without
        triggering lazy loads that violate async context.

        Args:
            team_id: ID of the team to retrieve.
            contest_id: Optional ID of the contest for context in error messages.

        Returns:
            The Team object if found with all relationships eagerly loaded.

        Raises:
            TeamNotFoundError: If the team with the given ID does not exist.
        """
        result = await self.db.execute(
            select(Team)
            .options(selectinload(Team.team_contests).selectinload(ContestTeam.contest))
            .filter(Team.id == team_id)
        )
        team = result.scalars().first()
        if not team:
            raise TeamNotFoundError(
                str(team_id), str(contest_id) if contest_id else "unknown"
            )
        return team

    async def get_contest_team_or_raise(
        self, contest_id: UUID, team_id: UUID
    ) -> ContestTeam:
        """
        Retrieve a ContestTeam by contest ID and team ID or raise an exception if not found.

        Args:
            contest_id: ID of the contest.
            team_id: ID of the team.
        Returns:
            The ContestTeam object if found.
        Raises:
            TeamNotFoundError: If the ContestTeam with the given contest ID and team ID
            does not exist.
        """
        result = await self.db.execute(
            select(ContestTeam)
            .options(joinedload(ContestTeam.team))
            .filter(
                ContestTeam.contest_id == contest_id,
                ContestTeam.team_id == team_id,
            )
        )
        contest_team = result.scalars().first()
        if not contest_team:
            raise TeamNotFoundError(str(team_id), str(contest_id))
        return contest_team

    async def get_team_members_or_raise(
        self, team_id: UUID, contest_id: UUID | None = None
    ) -> list[User]:
        """
        Retrieve the members of a team by team ID or raise an exception if not found.

        Args:
            team_id: ID of the team.
            contest_id: Optional ID of the contest for context in error messages.
        Returns:
            List of User objects representing the team members.
        Raises:
            TeamNotFoundError: If the team with the given ID does not exist.
        """
        result = await self.db.execute(select(Team).filter(Team.id == team_id))
        team = result.scalars().first()
        if not team:
            raise TeamNotFoundError(
                str(team_id), str(contest_id) if contest_id else "unknown"
            )
        member_result = await self.db.execute(
            select(User)
            .join(TeamUser, TeamUser.user_id == User.id)
            .filter(TeamUser.team_id == team_id)
        )
        members: list[User] = list(member_result.scalars().all())
        return members

    async def get_team_members_count_or_raise(
        self, team_id: UUID, contest_id: UUID | None = None
    ) -> int:
        """
        Retrieve the count of members in a team by team ID or raise an exception if not found.

        Args:
            team_id: ID of the team.
            contest_id: Optional ID of the contest for context in error messages.
        Returns:
            The count of team members.
        Raises:
            TeamNotFoundError: If the team with the given ID does not exist.
        """
        result = await self.db.execute(select(Team).filter(Team.id == team_id))
        team = result.scalars().first()
        if not team:
            raise TeamNotFoundError(
                str(team_id), str(contest_id) if contest_id else "unknown"
            )
        count_query = select(func.count()).select_from(
            select(TeamUser).filter(TeamUser.team_id == team_id).subquery()
        )
        member_count = (await self.db.execute(count_query)).scalar() or 0
        return int(member_count or 0)

    async def count_teams_in_contest(self, contest_id: UUID) -> int:
        """Count the number of teams registered in a contest.

        This method counts rows in the `contest_team` association table for the
        provided contest.

        Args:
            contest_id: Contest identifier.

        Returns:
            Total number of teams in the contest.
        """
        result = await self.db.execute(
            select(func.count())
            .select_from(ContestTeam)
            .filter(ContestTeam.contest_id == contest_id)
        )
        return int(result.scalar() or 0)

    async def count_participants_in_contest(self, contest_id: UUID) -> int:
        """Count the number of distinct participants in a contest.

        A participant is counted as a distinct user present in any team that is
        linked to the contest.

        Args:
            contest_id: Contest identifier.

        Returns:
            Total number of distinct users participating in the contest.
        """
        result = await self.db.execute(
            select(func.count(func.distinct(TeamUser.user_id)))
            .select_from(ContestTeam)
            .join(TeamUser, TeamUser.team_id == ContestTeam.team_id)
            .filter(ContestTeam.contest_id == contest_id)
        )
        return int(result.scalar() or 0)

    async def get_all_team_members(self, team_id: UUID) -> list[TeamUser]:
        """
        Retrieve all TeamUser records for a team without pagination.

        This method returns TeamUser objects which contain user_id references,
        useful for checking membership without loading full User data.

        Args:
            team_id: ID of the team

        Returns:
            List of all TeamUser objects for the team
        """
        result = await self.db.execute(
            select(TeamUser).filter(TeamUser.team_id == team_id)
        )
        return list(result.scalars().all())

    async def get_team_members_paginated(
        self,
        team_id: UUID,
        search_term: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, list[tuple[User, TeamUser]]]:
        """
        Retrieve team members with pagination and optional search filtering.

        Joins User and TeamUser tables to provide complete member information
        with support for text search by name or email.

        Args:
            team_id: ID of the team
            search_term: Optional text to search in member names or emails (case-insensitive)
            skip: Number of members to skip for pagination (default: 0)
            limit: Maximum members to return (default: 100)

        Returns:
            Tuple containing:
            - Total count of members matching the filters
            - List of (User, TeamUser) tuples for the requested page
        """
        # Build base query
        base_query = (
            select(User, TeamUser)
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
        count_query = select(func.count()).select_from(
            base_query.with_only_columns(User.id).subquery()
        )
        total = (await self.db.execute(count_query)).scalar_one()

        # Get paginated results
        result = await self.db.execute(base_query.offset(skip).limit(limit))
        results: list[tuple[User, TeamUser]] = [
            tuple(row) for row in result.all()
        ]  # List of (User, TeamUser) tuples

        return total, results

    async def add_team_members(
        self, team_id: UUID, member_ids: list[UUID], leader_id: UUID | None = None
    ) -> None:
        """
        Add members to a team and optionally update the team leader.

        This method encapsulates the database operations for adding team members,
        keeping the service layer clean and focused on business logic.

        Args:
            team_id: ID of the team to add members to
            member_ids: List of user IDs to add as team members
            leader_id: Optional new leader ID to update

        Returns:
            None - changes are flushed to the database
        """
        # Add new members
        for member_id in member_ids:
            team_user = TeamUser(team_id=team_id, user_id=member_id)
            self.db.add(team_user)

        # Update leader if specified
        if leader_id:
            result = await self.db.execute(select(Team).filter(Team.id == team_id))
            team = result.scalars().first()
            if team:
                team.leader_id = leader_id

        await self.db.flush()

    async def remove_team_members(self, team_id: UUID, member_ids: list[UUID]) -> None:
        """
        Remove members from a team.

        This method encapsulates the database operations for removing team members,
        keeping the service layer clean and focused on business logic.

        Args:
            team_id: ID of the team to remove members from
            member_ids: List of user IDs to remove from the team

        Returns:
            None - changes are flushed to the database
        """
        # Remove team members

        await self.db.execute(
            delete(TeamUser).where(
                TeamUser.team_id == team_id, TeamUser.user_id.in_(member_ids)
            )
        )

        await self.db.flush()

    async def get_contest_teams(
        self,
        contest_id: UUID,
        filters: TeamFilters,
        pagination: PaginationParams,
    ) -> PaginatedResult:
        """
        Retrieve teams for a contest with optional filtering and pagination.

        This method encapsulates the database query logic for retrieving teams,
        keeping the service layer clean and focused on business logic.

        Args:
            contest_id: ID of the contest to retrieve teams from
            filters: TeamFilters object containing optional search_term and status
            pagination: PaginationParams object containing skip and limit values

        Returns:
            PaginatedResult containing total count and list of ContestTeam objects
        """
        # Build base query with eager loading of team relationship
        base_query = (
            select(ContestTeam)
            .options(joinedload(ContestTeam.team))
            .join(Team, ContestTeam.team_id == Team.id)
            .filter(ContestTeam.contest_id == contest_id)
        )

        # Apply search filter if provided
        if filters.search_term:
            base_query = base_query.filter(Team.name.ilike(f"%{filters.search_term}%"))

        # Apply status filter if provided
        if filters.status:
            base_query = base_query.filter(ContestTeam.team_status == filters.status)

        # Get total count before pagination
        count_query = select(func.count()).select_from(
            base_query.with_only_columns(ContestTeam.contest_id).subquery()
        )
        total = (await self.db.execute(count_query)).scalar() or 0

        # Apply pagination
        result = await self.db.execute(
            base_query.offset(pagination.skip).limit(pagination.limit)
        )
        contest_teams = list(result.unique().scalars().all())

        return PaginatedResult(total=total, items=contest_teams)

    async def get_team_by_id(self, contest_id: UUID, team_id: UUID) -> ContestTeam:
        """
        Retrieve a specific team by ID within a contest.

        This method encapsulates the database query logic for retrieving a single team,
        keeping the service layer clean and focused on business logic.

        Args:
            contest_id: ID of the contest containing the team
            team_id: ID of the team to retrieve

        Returns:
            ContestTeam object with team relationship loaded

        Raises:
            TeamNotFoundError: If the team is not found in the contest
        """
        result = await self.db.execute(
            select(ContestTeam)
            .options(joinedload(ContestTeam.team))
            .filter(
                ContestTeam.contest_id == contest_id,
                ContestTeam.team_id == team_id,
            )
        )
        contest_team = result.scalars().first()

        if not contest_team:
            raise TeamNotFoundError(str(team_id), str(contest_id))

        return contest_team

    async def create_team(
        self,
        *,
        team: Team,
        contest_team: ContestTeam,
        progress: ContestTeamProgress,
        team_users: list[TeamUser],
    ) -> ContestTeam:
        """
        Create a new team in the database.

        Args:
            team_data: CreateTeamData object containing all team creation data

        Returns:
            The created ContestTeam object with its associated Team data loaded
        """
        self.db.add(team)
        self.db.add(contest_team)
        self.db.add(progress)
        self.db.add_all(team_users)

        await self.db.flush()  # Flush to save all changes and get IDs

        result = await self.db.execute(
            select(ContestTeam)
            .options(joinedload(ContestTeam.team))
            .filter(
                ContestTeam.team_id == team.id,
                ContestTeam.contest_id == contest_team.contest_id,
            )
        )
        created_contest_team: ContestTeam | None = result.scalar_one_or_none()
        if not created_contest_team:
            raise TeamNotFoundError(str(team.id), str(contest_team.contest_id))
        return created_contest_team

    async def update_team(self, team: Team, contest_team: ContestTeam) -> ContestTeam:
        """
        Update an existing team in the database.

        Args:
            team: Team object with updated data (must have valid ID)

        Returns:
            The updated ContestTeam object with its associated Team data loaded
        """
        await self.db.flush()  # Flush to save changes

        result = await self.db.execute(
            select(ContestTeam)
            .options(joinedload(ContestTeam.team))
            .filter(
                ContestTeam.team_id == team.id,
                ContestTeam.contest_id == contest_team.contest_id,
            )
        )
        updated_contest_team: ContestTeam | None = result.scalar_one_or_none()
        if not updated_contest_team:
            raise TeamNotFoundError(str(team.id), str(contest_team.contest_id))
        return updated_contest_team

    async def update_team_approval_status(
        self, contest_team: ContestTeam, approval_status: TeamApprovalStatus
    ) -> ContestTeam:
        """
        Update a team's approval status within a contest.

        Args:
            contest_team: ContestTeam object to update
            approval_status: New approval status to persist

        Returns:
            The updated ContestTeam object with team relationship loaded
        """
        contest_team.approval_status = approval_status
        await self.db.flush()

        result = await self.db.execute(
            select(ContestTeam)
            .options(joinedload(ContestTeam.team))
            .filter(
                ContestTeam.team_id == contest_team.team_id,
                ContestTeam.contest_id == contest_team.contest_id,
            )
        )
        updated_contest_team: ContestTeam | None = result.scalar_one_or_none()
        if not updated_contest_team:
            raise TeamNotFoundError(
                str(contest_team.team_id), str(contest_team.contest_id)
            )
        return updated_contest_team

    # ============ STUDENT-SPECIFIC METHODS ============

    async def get_user_teams(
        self,
        user_id: UUID,
        pagination: PaginationParams,
    ) -> PaginatedResult:
        """
        Retrieve all teams where a student is a member.

        Args:
            user_id: Student's user ID
            pagination: PaginationParams for skip/limit

        Returns:
            PaginatedResult with teams user is member of
        """
        # Count total teams for this user
        count_query = (
            select(func.count(Team.id))
            .join(TeamUser, TeamUser.team_id == Team.id)
            .filter(TeamUser.user_id == user_id)
        )
        total = (await self.db.execute(count_query)).scalar() or 0

        # Get paginated teams with eagerly loaded members and their users
        teams_query = (
            select(Team)
            .options(selectinload(Team.members).selectinload(TeamUser.user))
            .join(TeamUser, TeamUser.team_id == Team.id)
            .filter(TeamUser.user_id == user_id)
            .offset(pagination.skip)
            .limit(pagination.limit)
            .distinct()  # DISTINCT to avoid duplicate rows from the join
        )
        result = await self.db.execute(teams_query)
        teams = list(result.scalars().unique().all())

        return PaginatedResult(total=total, items=teams)

    async def get_available_teams_in_contest(
        self,
        contest_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Team]:
        """
        Retrieve teams in a contest that have available slots for joining.

        Args:
            contest_id: Contest ID
            skip: Pagination offset
            limit: Pagination limit

        Returns:
            List of Team objects with available slots
        """
        # Import here to avoid circular imports
        from app.models.contest import Contest

        # Get contest to retrieve max_team_size
        contest_result = await self.db.execute(
            select(Contest).where(Contest.id == contest_id)
        )
        contest = contest_result.scalar_one_or_none()

        if not contest:
            return []

        max_team_size = contest.max_team_size

        # Eagerly load members and their user details to avoid lazy loading later
        result = await self.db.execute(
            select(Team)
            .join(ContestTeam, ContestTeam.team_id == Team.id)
            .options(selectinload(Team.members).selectinload(TeamUser.user))
            .filter(ContestTeam.contest_id == contest_id)
            .offset(skip)
            .limit(limit)
        )
        teams: list[Team] = list(result.scalars().all())

        # Filter teams with available slots in memory
        available_teams = []
        for team in teams:
            member_count = len(team.members)
            if member_count < max_team_size:
                available_teams.append(team)

        return available_teams

    async def add_student_to_team(
        self,
        team_id: UUID,
        user_id: UUID,
    ) -> TeamUser:
        """
        Add a student to an existing team.

        Args:
            team_id: Team ID
            user_id: Student user ID to add

        Returns:
            Created TeamUser object
        """
        team_user = TeamUser(team_id=team_id, user_id=user_id)
        self.db.add(team_user)
        await self.db.flush()
        return team_user

    async def remove_student_from_team(
        self,
        team_id: UUID,
        user_id: UUID,
    ) -> None:
        """
        Remove a student from a team.

        Args:
            team_id: Team ID
            user_id: Student user ID to remove

        Returns:
            None
        """
        await self.db.execute(
            delete(TeamUser).filter(
                TeamUser.team_id == team_id,
                TeamUser.user_id == user_id,
            )
        )
        await self.db.flush()

    async def is_student_in_team(
        self,
        team_id: UUID,
        user_id: UUID,
    ) -> bool:
        """
        Check if a student is a member of a team.

        Args:
            team_id: Team ID
            user_id: Student user ID

        Returns:
            True if student is in team, False otherwise
        """
        result = await self.db.execute(
            select(TeamUser).filter(
                TeamUser.team_id == team_id,
                TeamUser.user_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_team_members_detailed(
        self,
        team_id: UUID,
    ) -> list[TeamUser]:
        """
        Retrieve all members of a team with full user details.

        Args:
            team_id: Team ID

        Returns:
            List of TeamUser objects with user data populated
        """
        result = await self.db.execute(
            select(TeamUser)
            .options(selectinload(TeamUser.user))
            .filter(TeamUser.team_id == team_id)
        )
        return list(result.scalars().all())

    async def create_student_team_for_contest(
        self,
        contest_id: UUID,
        team_name: str,
        team_description: str | None,
        created_by: UUID,
    ) -> tuple[Team, ContestTeam, ContestTeamProgress, TeamUser]:
        """
        Create a new team for student in a contest.

        Creates team, registers in contest, adds creator as member and leader,
        and initializes progress tracking.

        Args:
            contest_id: Contest ID
            team_name: Name for new team
            team_description: Optional team description
            created_by: Student user ID creating the team

        Returns:
            Tuple of (Team, ContestTeam, ContestTeamProgress, TeamUser)
        """
        # Create team
        team = Team(
            name=team_name,
            description=team_description,
            created_by=created_by,
            leader_id=created_by,
        )
        self.db.add(team)
        await self.db.flush()

        # Add creator as team member
        team_user = TeamUser(team_id=team.id, user_id=created_by)
        self.db.add(team_user)

        # Fetch contest to determine initial approval status
        contest_result = await self.db.execute(
            select(Contest).where(Contest.id == contest_id)
        )
        contest = contest_result.scalar_one_or_none()
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        # Determine initial approval status based on contest configuration
        from app.utils.enums import TeamApprovalMode

        if contest.team_approval_mode == TeamApprovalMode.AUTO_APPROVE:
            initial_approval_status = TeamApprovalStatus.APPROVED
            initial_team_status = TeamStatus.CONFIRMED
        else:  # INSTRUCTOR_REVIEW
            initial_approval_status = TeamApprovalStatus.WAITING
            initial_team_status = TeamStatus.DRAFT

        # Register team in contest
        contest_team = ContestTeam(
            contest_id=contest_id,
            team_id=team.id,
            team_status=initial_team_status,
            approval_status=initial_approval_status,
        )
        self.db.add(contest_team)

        # Create progress tracking
        progress = ContestTeamProgress(
            contest_id=contest_id,
            team_id=team.id,
            score=0,
        )
        self.db.add(progress)

        await self.db.flush()
        return team, contest_team, progress, team_user
