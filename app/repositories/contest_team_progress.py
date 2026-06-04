from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.contest import ContestTeamProgressNotFoundError
from app.models.contest import ContestTeamProgress


class ContestTeamProgressRepository:
    """
    Repository for contest team progress database operations.

    Attributes:
        db: The asynchronous database session.
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize the ContestTeamProgressRepository.

        Args:
            db: The asynchronous database session.
        """
        self.db = db

    async def get_contest_team_progress_by_id(
        self,
        contest_id: UUID,
        contest_team_id: UUID,
        contest_team_member_id: UUID | None = None,
        for_update: bool = False,
    ) -> ContestTeamProgress | None:
        """
        Fetch a single contest team progress record by contest ID, team ID, and optionally member ID.

        Args:
            contest_id: The UUID of the contest.
            contest_team_id: The UUID of the contest team.
            contest_team_member_id: The UUID of the contest team member.
            for_update: If True, acquires a row lock (SELECT ... FOR UPDATE).

        Returns:
            ContestTeamProgress | None: The progress record if found, otherwise None.
        """
        stmt = select(ContestTeamProgress).where(
            ContestTeamProgress.contest_id == contest_id,
            ContestTeamProgress.contest_team_id == contest_team_id,
        )
        if contest_team_member_id:
            stmt = stmt.where(
                ContestTeamProgress.contest_team_member_id == contest_team_member_id
            )
        else:
            stmt = stmt.where(ContestTeamProgress.contest_team_member_id.is_(None))

        if for_update:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        return result.scalars().one_or_none()

    async def get_contest_team_progress_or_raise(
        self,
        contest_id: UUID,
        contest_team_id: UUID,
        contest_team_member_id: UUID | None = None,
    ) -> ContestTeamProgress:
        """
        Retrieve a contest team progress record or raise an exception if not found.

        Args:
            contest_id: The UUID of the contest.
            contest_team_id: The UUID of the contest team.
            contest_team_member_id: The UUID of the contest team member.

        Returns:
            ContestTeamProgress: The found progress record.

        Raises:
            ContestTeamProgressNotFoundError: If the progress record does not exist.
        """
        progress = await self.get_contest_team_progress_by_id(
            contest_id, contest_team_id, contest_team_member_id
        )
        if not progress:
            raise ContestTeamProgressNotFoundError(
                str(contest_id), str(contest_team_id)
            )
        return progress

    async def create_contest_team_progress(
        self, progress: ContestTeamProgress
    ) -> ContestTeamProgress:
        """
        Create a new contest team progress record in the database.

        Args:
            progress: The ContestTeamProgress model instance to create.

        Returns:
            ContestTeamProgress: The created progress instance.
        """
        self.db.add(progress)
        await self.db.flush()
        return progress

    async def update_contest_team_progress(
        self, progress: ContestTeamProgress
    ) -> ContestTeamProgress:
        """
        Update an existing contest team progress record.

        Args:
            progress: The ContestTeamProgress model instance to update.

        Returns:
            ContestTeamProgress: The updated progress instance.
        """
        await self.db.flush()
        return progress
