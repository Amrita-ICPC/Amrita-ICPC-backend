from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, delete, desc, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.exceptions.contest import (
    ContestNotFoundError,
    ContestTeamMemberNotFoundException,
    QuestionNotInContestError,
)
from app.exceptions.team import TeamNotFoundError
from app.models.audience import Audience, ContestAudience, UserAudience
from app.models.contest import (
    Contest,
    ContestQuestion,
    ContestSubmission,
    ContestTeam,
    ContestTeamMember,
    ContestTeamProgress,
)
from app.models.language import Language
from app.models.question import Question, Submission, SubmissionTestCase
from app.models.team import Team, TeamUser
from app.models.user import User
from app.repositories.dto import (
    PaginatedResult,
    PaginationParams,
    TeamFilters,
)
from app.utils.enums import (
    ContestTeamMemberStatus,
    SubmissionStatus,
    TeamApprovalStatus,
    TeamStatus,
)


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

    async def get_contest_teams_count(self, contest_id: UUID) -> int:
        """
        Retrieve the number of teams in a specific contest.

        Args:
            contest_id: ID of the contest to retrieve the team count for.
        Returns:
            The number of teams in the contest.
        """
        result = await self.db.execute(
            select(func.count(ContestTeam.team_id)).filter(
                ContestTeam.contest_id == contest_id
            )
        )
        return result.scalars().first() or 0

    async def get_contest_team_by_id(
        self, contest_id: UUID, team_id: UUID
    ) -> ContestTeam | None:
        """
        Retrieve the team details for a specific contest.

        Args:
            contest_id: ID of the contest to retrieve the team details for.
            team_id: ID of the team to retrieve the team details for.
        Returns:
            The Team object if found, otherwise None.
        """
        result = await self.db.execute(
            select(ContestTeam).filter(
                ContestTeam.team_id == team_id, ContestTeam.contest_id == contest_id
            )
        )
        return result.scalars().first()

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
            .options(
                joinedload(ContestTeam.team)
                .selectinload(Team.members)
                .selectinload(TeamUser.user)
            )
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
            .where(ContestTeam.team_status == TeamStatus.CONFIRMED)
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
            .where(ContestTeam.team_status == TeamStatus.CONFIRMED)
        )
        return int(result.scalar() or 0)

    async def count_flagged_progress_in_contest(self, contest_id: UUID) -> int:
        """Count flagged team/member progress records in a contest.

        A progress record is flagged when `flagged_at` is set.

        Args:
            contest_id: Contest identifier.

        Returns:
            Total number of flagged progress records for the contest.
        """
        result = await self.db.execute(
            select(func.count())
            .select_from(ContestTeamProgress)
            .where(
                ContestTeamProgress.contest_id == contest_id,
                ContestTeamProgress.flagged_at.is_not(None),
            )
        )
        return int(result.scalar() or 0)

    async def get_team_status_counts(self, contest_id: UUID) -> dict[str, int]:
        """
        Get counts of teams by status and approval status in a contest.

        Args:
            contest_id: ID of the contest

        Returns:
            Dictionary containing counts for approved, waiting, rejected, and disqualified teams.
        """
        # Count by TeamApprovalStatus
        approval_query = (
            select(ContestTeam.approval_status, func.count(ContestTeam.team_id))
            .filter(ContestTeam.contest_id == contest_id)
            .group_by(ContestTeam.approval_status)
        )
        approval_results = await self.db.execute(approval_query)
        approval_counts = {status: count for status, count in approval_results.all()}

        # Count by TeamStatus.DISQUALIFIED
        disqualified_query = select(func.count(ContestTeam.team_id)).filter(
            ContestTeam.contest_id == contest_id,
            ContestTeam.team_status == TeamStatus.DISQUALIFIED,
        )
        disqualified_count = (await self.db.execute(disqualified_query)).scalar() or 0

        return {
            "approved_count": approval_counts.get(TeamApprovalStatus.APPROVED, 0),
            "waiting_count": approval_counts.get(TeamApprovalStatus.WAITING, 0),
            "rejected_count": approval_counts.get(TeamApprovalStatus.REJECTED, 0),
            "disqualified_count": int(disqualified_count),
        }

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
        # Build base query with eager loading of team and its members
        base_query = (
            select(ContestTeam)
            .options(
                joinedload(ContestTeam.team)
                .selectinload(Team.members)
                .selectinload(TeamUser.user)
            )
            .join(Team, ContestTeam.team_id == Team.id)
            .filter(ContestTeam.contest_id == contest_id)
            .where(
                and_(
                    ContestTeam.team_status != TeamStatus.DRAFT,
                    ContestTeam.team_status != TeamStatus.CANCELLED,
                )
            )
        )

        # Apply search filter if provided
        if filters.search_term:
            base_query = base_query.filter(Team.name.ilike(f"%{filters.search_term}%"))

        # Apply status filter if provided
        if filters.status:
            base_query = base_query.filter(ContestTeam.team_status == filters.status)

        # Apply approval status filter if provided
        if filters.approval_status:
            base_query = base_query.filter(
                ContestTeam.approval_status == filters.approval_status
            )

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
            .options(
                joinedload(ContestTeam.team)
                .selectinload(Team.members)
                .selectinload(TeamUser.user)
            )
            .filter(
                ContestTeam.contest_id == contest_id,
                ContestTeam.team_id == team_id,
            )
        )
        contest_team = result.scalars().first()

        if not contest_team:
            raise TeamNotFoundError(str(team_id), str(contest_id))

        return contest_team

    def _build_submission_status_subquery(
        self,
        *,
        contest_id: UUID,
        contest_team_id: UUID | None = None,
        contest_team_member_id: UUID | None = None,
        question_id: UUID | None = None,
    ):
        """Build one row per contest submission with its computed final status."""
        filters = [ContestSubmission.contest_id == contest_id]
        if contest_team_id is not None:
            filters.append(ContestSubmission.contest_team_id == contest_team_id)
        if contest_team_member_id is not None:
            filters.append(
                ContestSubmission.contest_team_member_id == contest_team_member_id
            )
        if question_id is not None:
            filters.append(Submission.question_id == question_id)

        return (
            select(
                ContestSubmission.contest_team_id,
                ContestSubmission.contest_team_member_id,
                Submission.question_id,
                Submission.id.label("submission_id"),
                Submission.is_evaluated,
                case(
                    (Submission.is_evaluated.is_(False), None),
                    (
                        func.count(SubmissionTestCase.submission_id) == 0,
                        SubmissionStatus.SYSTEM_ERROR,
                    ),
                    (
                        func.sum(
                            case(
                                (
                                    SubmissionTestCase.status
                                    == SubmissionStatus.SYSTEM_ERROR,
                                    1,
                                ),
                                else_=0,
                            )
                        )
                        > 0,
                        SubmissionStatus.SYSTEM_ERROR,
                    ),
                    (
                        func.sum(
                            case(
                                (SubmissionTestCase.status == SubmissionStatus.CE, 1),
                                else_=0,
                            )
                        )
                        > 0,
                        SubmissionStatus.CE,
                    ),
                    (
                        func.sum(
                            case(
                                (SubmissionTestCase.status == SubmissionStatus.MLE, 1),
                                else_=0,
                            )
                        )
                        > 0,
                        SubmissionStatus.MLE,
                    ),
                    (
                        func.sum(
                            case(
                                (SubmissionTestCase.status == SubmissionStatus.TLE, 1),
                                else_=0,
                            )
                        )
                        > 0,
                        SubmissionStatus.TLE,
                    ),
                    (
                        func.sum(
                            case(
                                (SubmissionTestCase.status == SubmissionStatus.RE, 1),
                                else_=0,
                            )
                        )
                        > 0,
                        SubmissionStatus.RE,
                    ),
                    (
                        func.sum(
                            case(
                                (SubmissionTestCase.status == SubmissionStatus.WA, 1),
                                else_=0,
                            )
                        )
                        > 0,
                        SubmissionStatus.WA,
                    ),
                    else_=SubmissionStatus.AC,
                ).label("computed_status"),
            )
            .select_from(ContestSubmission)
            .join(Submission, ContestSubmission.submission_id == Submission.id)
            .outerjoin(
                SubmissionTestCase,
                SubmissionTestCase.submission_id == Submission.id,
            )
            .where(*filters)
            .group_by(
                ContestSubmission.contest_team_id,
                ContestSubmission.contest_team_member_id,
                Submission.question_id,
                Submission.id,
                Submission.is_evaluated,
            )
            .subquery()
        )

    def _submission_status_count(
        self, submission_status_subq: Any, status: SubmissionStatus
    ):
        return func.coalesce(
            func.sum(
                case(
                    (
                        and_(
                            submission_status_subq.c.is_evaluated.is_(True),
                            submission_status_subq.c.computed_status == status,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        )

    def _submission_statistics_columns(
        self,
        submission_status_subq: Any,
        *,
        total_label: str,
        accepted_label: str,
        pending_label: str,
    ) -> list[Any]:
        return [
            func.count(submission_status_subq.c.submission_id).label(total_label),
            self._submission_status_count(
                submission_status_subq, SubmissionStatus.AC
            ).label(accepted_label),
            self._submission_status_count(
                submission_status_subq, SubmissionStatus.WA
            ).label("wrong_answer"),
            self._submission_status_count(
                submission_status_subq, SubmissionStatus.TLE
            ).label("time_limit_exceeded"),
            self._submission_status_count(
                submission_status_subq, SubmissionStatus.RE
            ).label("runtime_error"),
            self._submission_status_count(
                submission_status_subq, SubmissionStatus.CE
            ).label("compilation_error"),
            self._submission_status_count(
                submission_status_subq, SubmissionStatus.MLE
            ).label("memory_limit_exceeded"),
            self._submission_status_count(
                submission_status_subq, SubmissionStatus.SYSTEM_ERROR
            ).label("system_error"),
            func.coalesce(
                func.sum(
                    case(
                        (submission_status_subq.c.is_evaluated.is_(False), 1),
                        else_=0,
                    )
                ),
                0,
            ).label(pending_label),
        ]

    @staticmethod
    def _progress_member_match(is_leader_only: bool):
        """Build the ``ContestTeamProgress`` <-> member join predicate.

        For ``LEADER_ONLY`` contests the session is stored as a single
        team-level progress row (``contest_team_member_id IS NULL``), so it must
        attach to every accepted member of the team. For
        ``INDIVIDUAL_WORKSPACE`` each member has their own progress row and is
        matched by id. This mirrors the write-side ``member_id_filter`` logic in
        the student contest-session service so the read side finds the same row
        that was created.
        """
        if is_leader_only:
            return ContestTeamProgress.contest_team_member_id.is_(None)
        return ContestTeamProgress.contest_team_member_id == ContestTeamMember.id

    async def get_contest_team_analytics(
        self, contest_id: UUID, contest_team_id: UUID, is_leader_only: bool = False
    ) -> tuple[Any, list[Any]]:
        """
        Fetch team analytics with aggregate submission status counts and member progress.

        The submission status subquery is scoped to one contest team so the database
        only groups relevant submissions and test cases.
        """
        submission_status_subq = self._build_submission_status_subquery(
            contest_id=contest_id,
            contest_team_id=contest_team_id,
        )
        team_counts_subq = (
            select(
                submission_status_subq.c.contest_team_id,
                *self._submission_statistics_columns(
                    submission_status_subq,
                    total_label="total_submissions",
                    accepted_label="accepted_submission",
                    pending_label="pending_submission",
                ),
            )
            .group_by(submission_status_subq.c.contest_team_id)
            .subquery()
        )

        team_result = await self.db.execute(
            select(
                ContestTeam.id.label("contest_team_id"),
                ContestTeam.name,
                func.coalesce(func.round(func.avg(ContestTeamProgress.score)), 0).label(
                    "score"
                ),
                func.coalesce(team_counts_subq.c.total_submissions, 0).label(
                    "total_submissions"
                ),
                func.coalesce(team_counts_subq.c.accepted_submission, 0).label(
                    "accepted_submission"
                ),
                func.coalesce(team_counts_subq.c.wrong_answer, 0).label("wrong_answer"),
                func.coalesce(team_counts_subq.c.time_limit_exceeded, 0).label(
                    "time_limit_exceeded"
                ),
                func.coalesce(team_counts_subq.c.runtime_error, 0).label(
                    "runtime_error"
                ),
                func.coalesce(team_counts_subq.c.compilation_error, 0).label(
                    "compilation_error"
                ),
                func.coalesce(team_counts_subq.c.memory_limit_exceeded, 0).label(
                    "memory_limit_exceeded"
                ),
                func.coalesce(team_counts_subq.c.system_error, 0).label("system_error"),
                func.coalesce(team_counts_subq.c.pending_submission, 0).label(
                    "pending_submission"
                ),
            )
            .select_from(ContestTeam)
            .outerjoin(
                ContestTeamMember,
                and_(
                    ContestTeamMember.contest_team_id == ContestTeam.id,
                    ContestTeamMember.status == ContestTeamMemberStatus.ACCEPTED,
                ),
            )
            .outerjoin(
                ContestTeamProgress,
                and_(
                    ContestTeamProgress.contest_id == contest_id,
                    ContestTeamProgress.contest_team_id == ContestTeam.id,
                    self._progress_member_match(is_leader_only),
                ),
            )
            .outerjoin(
                team_counts_subq,
                team_counts_subq.c.contest_team_id == ContestTeam.id,
            )
            .where(
                ContestTeam.id == contest_team_id,
                ContestTeam.contest_id == contest_id,
            )
            .group_by(
                ContestTeam.id,
                ContestTeam.name,
                team_counts_subq.c.total_submissions,
                team_counts_subq.c.accepted_submission,
                team_counts_subq.c.wrong_answer,
                team_counts_subq.c.time_limit_exceeded,
                team_counts_subq.c.runtime_error,
                team_counts_subq.c.compilation_error,
                team_counts_subq.c.memory_limit_exceeded,
                team_counts_subq.c.system_error,
                team_counts_subq.c.pending_submission,
            )
        )
        team_row = team_result.one_or_none()
        if team_row is None:
            raise TeamNotFoundError(str(contest_team_id), str(contest_id))

        member_result = await self.db.execute(
            select(
                User.id.label("id"),
                ContestTeamMember.id.label("contest_team_member_id"),
                User.name,
                User.email,
                func.coalesce(ContestTeamProgress.score, 0).label("score"),
                (ContestTeamProgress.flagged_at.is_not(None)).label("is_flagged"),
                ContestTeamProgress.flagged_reason,
                ContestTeamProgress.created_at.label("started_at"),
                ContestTeamProgress.ended_at,
                (ContestTeamProgress.id.is_not(None)).label("is_participated"),
                (ContestTeam.leader_id == ContestTeamMember.user_id).label("is_leader"),
            )
            .select_from(ContestTeamMember)
            .join(ContestTeam, ContestTeamMember.contest_team_id == ContestTeam.id)
            .join(User, ContestTeamMember.user_id == User.id)
            .outerjoin(
                ContestTeamProgress,
                and_(
                    ContestTeamProgress.contest_id == contest_id,
                    ContestTeamProgress.contest_team_id == contest_team_id,
                    self._progress_member_match(is_leader_only),
                ),
            )
            .where(
                ContestTeam.id == contest_team_id,
                ContestTeam.contest_id == contest_id,
                ContestTeamMember.status == ContestTeamMemberStatus.ACCEPTED,
            )
            .order_by(desc("is_leader"), User.name)
        )

        return team_row, list(member_result.all())

    async def has_contest_team_member_progress(
        self,
        contest_team_id: UUID,
        contest_team_member_id: UUID,
        is_leader_only: bool = False,
    ) -> bool:
        """Return whether the contest team member has started/attempted the contest.

        For ``LEADER_ONLY`` contests progress is recorded once at the team level
        (``contest_team_member_id IS NULL``), so any accepted member of a team
        with a team-level progress row counts as having started.
        """
        member_filter = (
            ContestTeamProgress.contest_team_member_id.is_(None)
            if is_leader_only
            else ContestTeamProgress.contest_team_member_id == contest_team_member_id
        )
        result = await self.db.execute(
            select(ContestTeamProgress.id)
            .where(
                ContestTeamProgress.contest_team_id == contest_team_id,
                member_filter,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_contest_team_member_detail(
        self,
        *,
        contest_id: UUID,
        contest_team_id: UUID,
        contest_team_member_id: UUID,
        is_leader_only: bool = False,
    ) -> Any:
        """Fetch one contest team member with participation and aggregate stats."""
        submission_status_subq = self._build_submission_status_subquery(
            contest_id=contest_id,
            contest_team_id=contest_team_id,
            contest_team_member_id=contest_team_member_id,
        )
        submission_stats_subq = (
            select(
                *self._submission_statistics_columns(
                    submission_status_subq,
                    total_label="total",
                    accepted_label="accepted",
                    pending_label="pending",
                )
            )
            .select_from(submission_status_subq)
            .subquery()
        )

        question_submission_counts_subq = (
            select(
                submission_status_subq.c.question_id,
                func.count(submission_status_subq.c.submission_id).label(
                    "total_submission"
                ),
                self._submission_status_count(
                    submission_status_subq, SubmissionStatus.AC
                ).label("accepted_submission"),
            )
            .group_by(submission_status_subq.c.question_id)
            .subquery()
        )

        question_stats_subq = (
            select(
                func.count(question_submission_counts_subq.c.question_id).label(
                    "attempted"
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                question_submission_counts_subq.c.accepted_submission
                                > 0,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("solved"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    question_submission_counts_subq.c.total_submission
                                    > 0,
                                    question_submission_counts_subq.c.accepted_submission
                                    == 0,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("unsolved"),
            )
            .select_from(question_submission_counts_subq)
            .subquery()
        )

        result = await self.db.execute(
            select(
                ContestTeamMember.id.label("contest_team_member_id"),
                ContestTeamMember.user_id,
                User.name,
                User.email,
                (ContestTeam.leader_id == ContestTeamMember.user_id).label("is_leader"),
                (ContestTeamProgress.id.is_not(None)).label("is_participated"),
                func.coalesce(ContestTeamProgress.score, 0).label("score"),
                ContestTeamProgress.created_at.label("started_at"),
                ContestTeamProgress.end_time.label("base_end_time"),
                ContestTeamProgress.ended_at,
                func.coalesce(ContestTeamProgress.extra_time_seconds, 0).label(
                    "extra_time_seconds"
                ),
                (ContestTeamProgress.flagged_at.is_not(None)).label("is_flagged"),
                ContestTeamProgress.flagged_at,
                ContestTeamProgress.flagged_reason,
                func.coalesce(submission_stats_subq.c.total, 0).label("total"),
                func.coalesce(submission_stats_subq.c.accepted, 0).label("accepted"),
                func.coalesce(submission_stats_subq.c.wrong_answer, 0).label(
                    "wrong_answer"
                ),
                func.coalesce(submission_stats_subq.c.time_limit_exceeded, 0).label(
                    "time_limit_exceeded"
                ),
                func.coalesce(submission_stats_subq.c.runtime_error, 0).label(
                    "runtime_error"
                ),
                func.coalesce(submission_stats_subq.c.memory_limit_exceeded, 0).label(
                    "memory_limit_exceeded"
                ),
                func.coalesce(submission_stats_subq.c.compilation_error, 0).label(
                    "compilation_error"
                ),
                func.coalesce(submission_stats_subq.c.system_error, 0).label(
                    "system_error"
                ),
                func.coalesce(submission_stats_subq.c.pending, 0).label("pending"),
                func.coalesce(question_stats_subq.c.attempted, 0).label("attempted"),
                func.coalesce(question_stats_subq.c.solved, 0).label("solved"),
                func.coalesce(question_stats_subq.c.unsolved, 0).label("unsolved"),
            )
            .select_from(ContestTeamMember)
            .join(ContestTeam, ContestTeamMember.contest_team_id == ContestTeam.id)
            .join(User, ContestTeamMember.user_id == User.id)
            .outerjoin(
                ContestTeamProgress,
                and_(
                    ContestTeamProgress.contest_id == contest_id,
                    ContestTeamProgress.contest_team_id == contest_team_id,
                    self._progress_member_match(is_leader_only),
                ),
            )
            .outerjoin(submission_stats_subq, true())
            .outerjoin(question_stats_subq, true())
            .where(
                ContestTeam.id == contest_team_id,
                ContestTeam.contest_id == contest_id,
                ContestTeamMember.id == contest_team_member_id,
            )
        )
        row = result.one_or_none()
        if row is None:
            raise ContestTeamMemberNotFoundException(str(contest_team_member_id))
        return row

    async def get_contest_team_member_question_analytics(
        self,
        *,
        contest_id: UUID,
        contest_team_id: UUID,
        contest_team_member_id: UUID,
    ) -> list[Any]:
        """Fetch all contest questions with this member's submission counts."""
        submission_status_subq = self._build_submission_status_subquery(
            contest_id=contest_id,
            contest_team_id=contest_team_id,
            contest_team_member_id=contest_team_member_id,
        )
        submission_stats_columns = self._submission_statistics_columns(
            submission_status_subq,
            total_label="total_submission",
            accepted_label="accepted_submission",
            pending_label="pending_submission",
        )
        submission_counts_subq = (
            select(
                submission_status_subq.c.question_id,
                submission_stats_columns[0],
                submission_stats_columns[1],
            )
            .group_by(submission_status_subq.c.question_id)
            .subquery()
        )

        result = await self.db.execute(
            select(
                Question.id.label("question_id"),
                Question.title,
                Question.difficulty,
                Question.time_limit_ms,
                Question.memory_limit_mb,
                func.coalesce(submission_counts_subq.c.total_submission, 0).label(
                    "total_submission"
                ),
                func.coalesce(submission_counts_subq.c.accepted_submission, 0).label(
                    "accepted_submission"
                ),
            )
            .select_from(ContestQuestion)
            .join(Question, ContestQuestion.question_id == Question.id)
            .outerjoin(
                submission_counts_subq,
                submission_counts_subq.c.question_id == Question.id,
            )
            .where(ContestQuestion.contest_id == contest_id)
            .order_by(ContestQuestion.order, Question.title)
        )
        return list(result.all())

    async def get_contest_team_member_question_submissions(
        self,
        *,
        contest_id: UUID,
        contest_team_id: UUID,
        contest_team_member_id: UUID,
        question_id: UUID,
    ) -> tuple[Any, Any, list[Any]]:
        """Fetch one question, its member submission statistics, and submissions."""
        question_result = await self.db.execute(
            select(
                Question.id.label("question_id"),
                Question.title.label("question_title"),
            )
            .select_from(ContestQuestion)
            .join(Question, ContestQuestion.question_id == Question.id)
            .where(
                ContestQuestion.contest_id == contest_id,
                ContestQuestion.question_id == question_id,
            )
        )
        question_row = question_result.one_or_none()
        if question_row is None:
            raise QuestionNotInContestError(str(question_id), str(contest_id))

        submission_status_subq = self._build_submission_status_subquery(
            contest_id=contest_id,
            contest_team_id=contest_team_id,
            contest_team_member_id=contest_team_member_id,
            question_id=question_id,
        )
        stats_result = await self.db.execute(
            select(
                *self._submission_statistics_columns(
                    submission_status_subq,
                    total_label="total",
                    accepted_label="accepted",
                    pending_label="pending",
                )
            ).select_from(submission_status_subq)
        )
        stats_row = stats_result.one()

        submissions_result = await self.db.execute(
            select(
                Submission.id.label("submission_id"),
                submission_status_subq.c.computed_status.label("status"),
                Submission.score,
                Language.name.label("language"),
                Submission.created_at,
                Submission.total_time.label("execution_time"),
                Submission.total_memory.label("memory"),
            )
            .select_from(submission_status_subq)
            .join(Submission, submission_status_subq.c.submission_id == Submission.id)
            .join(Language, Submission.language_id == Language.id)
            .order_by(Submission.created_at.desc())
        )

        return question_row, stats_row, list(submissions_result.all())

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
            .options(
                joinedload(ContestTeam.team)
                .selectinload(Team.members)
                .selectinload(TeamUser.user)
            )
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
            .options(
                joinedload(ContestTeam.team)
                .selectinload(Team.members)
                .selectinload(TeamUser.user)
            )
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

    async def update_team_status(
        self, contest_team: ContestTeam, status: TeamStatus
    ) -> ContestTeam:
        """
        Update a team's status (DRAFT, CONFIRMED, DISQUALIFIED) within a contest.

        Args:
            contest_team: ContestTeam object to update
            status: New status to persist

        Returns:
            The updated ContestTeam object with team relationship loaded
        """
        contest_team.team_status = status
        await self.db.flush()

        result = await self.db.execute(
            select(ContestTeam)
            .options(
                joinedload(ContestTeam.team)
                .selectinload(Team.members)
                .selectinload(TeamUser.user)
            )
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

    async def get_user_audience_for_contest(
        self,
        user_id: UUID,
        contest_id: UUID,
    ) -> Audience | None:
        """
        Get the audience that a user belongs to for a specific contest.

        Args:
            user_id: User ID
            contest_id: Contest ID

        Returns:
            Audience object if user belongs to an audience linked to contest, else None
        """
        result = await self.db.execute(
            select(Audience)
            .join(UserAudience, UserAudience.audience_id == Audience.id)
            .join(
                ContestAudience,
                ContestAudience.audience_id == Audience.id,
            )
            .filter(
                UserAudience.user_id == user_id,
                ContestAudience.contest_id == contest_id,
            )
        )
        return result.scalars().first()

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
        audience_id: UUID | None = None,
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
            audience_id: Optional audience the team is associated with

        Returns:
            Tuple of (Team, ContestTeam, ContestTeamProgress, TeamUser)
        """
        # Create team
        team = Team(
            name=team_name,
            description=team_description,
            created_by=created_by,
            leader_id=created_by,
            audience_id=audience_id,
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
