from uuid import UUID

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions.contest import (
    ContestTeamMemberNotFoundException,
    ContestTeamNotFoundException,
)
from app.models import ContestTeam, ContestTeamMember, Team, User
from app.repositories.dto import PaginatedResult, PaginationParams, TeamFilters
from app.utils.enums import ContestTeamMemberStatus, TeamApprovalStatus, TeamStatus


class ContestTeamRepository:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_contest_team(self, contest_team: ContestTeam) -> ContestTeam:
        """Create a new contest team association record in the database.

        Args:
            contest_team: The ContestTeam model instance to save.

        Returns:
            ContestTeam: The persisted and refreshed ContestTeam model instance.
        """
        self.db.add(contest_team)
        await self.db.flush()
        await self.db.refresh(contest_team)
        return contest_team

    async def create_contest_team_members(
        self, contest_team_members: list[ContestTeamMember]
    ) -> list[ContestTeamMember]:
        """Bulk create contest team member records.

        Args:
            contest_team_members: List of ContestTeamMember model instances.

        Returns:
            list[ContestTeamMember]: The list of created ContestTeamMember instances.
        """
        self.db.add_all(contest_team_members)
        await self.db.flush()
        return contest_team_members

    async def get_contest_team_by_id_or_raise(self, contest_team_id: UUID) -> ContestTeam:
        """Get a contest team by its ID or raise an exception if not found.

        Args:
            contest_team_id: The ID of the contest team to retrieve.

        Returns:
            ContestTeam: The contest team with the specified ID.

        Raises:
            ContestTeamNotFoundException: If no contest team is found with the given ID.
        """
        stmt = (
            select(ContestTeam)
            .options(
                selectinload(ContestTeam.team)
                .selectinload(Team.members)
            )
            .where(ContestTeam.id == contest_team_id)
        )
        result = await self.db.execute(stmt)
        contest_team = result.scalar_one_or_none()
        if contest_team is None:
            raise ContestTeamNotFoundException(f"Contest team not found with ID: {contest_team_id}")
        return contest_team

    async def update_contest_team(self, contest_team: ContestTeam) -> ContestTeam:
        """Update an existing contest team record in the database.

        Args:
            contest_team: The ContestTeam model instance to update.

        Returns:
            ContestTeam: The updated and refreshed ContestTeam model instance.
        """
        self.db.add(contest_team)
        await self.db.flush()
        await self.db.refresh(contest_team)
        return contest_team

    async def count_contest_team_members(
        self,
        contest_team_id: UUID,
        contest_team_member_statuses: list[ContestTeamMemberStatus] | ContestTeamMemberStatus | None = None,
    ) -> int:
        """Count the number of members in a contest team.

        Args:
            contest_team_id: The ID of the contest team.
            contest_team_member_statuses: The status or list of statuses to filter by.

        Returns:
            int: The number of members in the contest team.
        """
        stmt = (
            select(func.count(ContestTeamMember.id))
            .where(ContestTeamMember.contest_team_id == contest_team_id)
        )

        if contest_team_member_statuses is not None:
            if isinstance(contest_team_member_statuses, list):
                stmt = stmt.where(ContestTeamMember.status.in_(contest_team_member_statuses))
            else:
                stmt = stmt.where(ContestTeamMember.status == contest_team_member_statuses)

        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def get_contest_team_member_by_user_id(self, user_id: UUID, stauts: ContestTeamMemberStatus | None) -> ContestTeamMember | None:
        """Get the contest team member record for a given user ID.

        Args:
            user_id: The ID of the user.
            status: The status of the contest team member.
        Returns:
            ContestTeamMember: The contest team member record associated with the user ID, or None if
            not found.
        """
        stmt = (
            select(ContestTeamMember)
            .where(ContestTeamMember.user_id == user_id)
            .options(
                selectinload(ContestTeamMember.contest),
                selectinload(ContestTeamMember.contest_team).selectinload(ContestTeam.contest_team_member).selectinload(ContestTeamMember.user)
            ).order_by(
        case(
        (ContestTeamMember.status == ContestTeamMemberStatus.INVITED, 1),
        (ContestTeamMember.status == ContestTeamMemberStatus.ACCEPTED, 2),
        (ContestTeamMember.status == ContestTeamMemberStatus.LEFT, 3),
        (ContestTeamMember.status == ContestTeamMemberStatus.REJECTED, 4),
        (ContestTeamMember.status == ContestTeamMemberStatus.REMOVED, 5),
        (ContestTeamMember.status == ContestTeamMemberStatus.CANCELLED, 6),
         ),
        ))
        if stauts is not None:
            stmt = stmt.where(ContestTeamMember.status == stauts)

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def count_teams(self, contest_id: UUID, status: TeamStatus, approval_status: TeamApprovalStatus) -> int:
        """Count the number of teams in a contest with the specified status and approval status.

        Args:
            contest_id: The ID of the contest.
            status: The status of the team.
            approval_status: The approval status of the team.
        Returns:
            int: The number of teams in the contest with the specified status and approval status.
        """
        stmt = (
            select(func.count(ContestTeam.id))
            .where(ContestTeam.contest_id == contest_id)
            .where(ContestTeam.team_status == status)
            .where(ContestTeam.approval_status == approval_status)
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def count_teams_by_status(self, contest_id: UUID) -> dict[str, int]:
        """Count the number of approved, waiting, disqualified, and rejected teams in a contest.

        Args:
            contest_id: The ID of the contest.

        Returns:
            dict[str, int]: A dictionary containing counts for approved, waiting, disqualified, and rejected teams.
        """
        stmt = (
            select(
                func.sum(case((ContestTeam.approval_status == TeamApprovalStatus.APPROVED, 1), else_=0)).label("approved"),
                func.sum(case((and_(ContestTeam.approval_status == TeamApprovalStatus.WAITING, ContestTeam.team_status == TeamStatus.CONFIRMED), 1), else_=0)).label("waiting"),
                func.sum(case((ContestTeam.approval_status == TeamApprovalStatus.REJECTED, 1), else_=0)).label("rejected"),
                func.sum(case((ContestTeam.team_status == TeamStatus.DISQUALIFIED, 1), else_=0)).label("disqualified"),
            )
            .where(ContestTeam.contest_id == contest_id)
        )
        result = await self.db.execute(stmt)
        row = result.one()
        return {
            "approved_count": int(row.approved or 0),
            "waiting_count": int(row.waiting or 0),
            "rejected_count": int(row.rejected or 0),
            "disqualified_count": int(row.disqualified or 0),
        }

    async def get_contest_team_member_or_raise(self, contest_team_member_id: UUID) -> ContestTeamMember:
        """Get a contest team member by its ID or raise an exception if not found.

        Args:
            contest_team_member_id: The ID of the contest team member.

        Returns:
            ContestTeamMember: The contest team member with the specified ID.

        Raises:
            ContestTeamMemberNotFoundException: If no contest team member is found with the given ID.
        """
        stmt = (
            select(ContestTeamMember)
            .where(ContestTeamMember.id == contest_team_member_id)
        )
        result = await self.db.execute(stmt)
        contest_team_member = result.scalar_one_or_none()
        if contest_team_member is None:
            raise ContestTeamMemberNotFoundException(f"Contest team member not found with ID: {contest_team_member_id}")
        return contest_team_member

    async def update_contest_team_member(self, contest_team_member: ContestTeamMember) -> ContestTeamMember:
        """Update an existing contest team member record in the database.

        Args:
            contest_team_member: The ContestTeamMember model instance to update.

        Returns:
            ContestTeamMember: The updated and refreshed ContestTeamMember model instance.
        """
        self.db.add(contest_team_member)
        await self.db.flush()
        await self.db.refresh(contest_team_member)
        return contest_team_member

    async def get_contest_team_members(self, contest_team_id:UUID, contestTeamMemberStatus: list[ContestTeamMemberStatus] | None = None, user_ids:list[UUID] | None = None )->list[ContestTeamMember]:
        query = (select(ContestTeamMember).where(ContestTeamMember.contest_team_id == contest_team_id))

        if contestTeamMemberStatus is not None:
            query = query.where(ContestTeamMember.status.in_(contestTeamMemberStatus))

        if user_ids is not None:
            query = query.where(ContestTeamMember.user_id.in_(user_ids))

        query = query.options(selectinload(ContestTeamMember.user))

        result = await self.db.execute(query)

        return list(result.scalars())

    async def get_active_members_in_contest(self, contest_id: UUID, user_ids: list[UUID]) -> list[ContestTeamMember]:
        """Get active (INVITED or ACCEPTED) contest team members for a list of users in a contest."""
        stmt = (
            select(ContestTeamMember)
            .where(
                and_(
                    ContestTeamMember.contest_id == contest_id,
                    ContestTeamMember.user_id.in_(user_ids),
                    ContestTeamMember.status.in_([ContestTeamMemberStatus.INVITED, ContestTeamMemberStatus.ACCEPTED])
                )
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars())

    async def update_contest_team_members_status(
        self,
        contest_team_id: UUID,
        from_statuses: list[ContestTeamMemberStatus],
        to_status: ContestTeamMemberStatus,
        exclude_user_id: UUID | None = None,
    ) -> None:
        """Bulk update status of contest team members."""
        from sqlalchemy import update
        stmt = (
            update(ContestTeamMember)
            .where(ContestTeamMember.contest_team_id == contest_team_id)
            .where(ContestTeamMember.status.in_(from_statuses))
            .values(status=to_status)
        )
        if exclude_user_id is not None:
            stmt = stmt.where(ContestTeamMember.user_id != exclude_user_id)

        await self.db.execute(stmt)
        await self.db.flush()

    async def get_contest_teams(
        self,
        contest_id: UUID,
        filters: TeamFilters,
        pagination: PaginationParams,
    ) -> PaginatedResult:
        """Retrieve paginated and filtered list of contest teams for a contest.

        Args:
            contest_id: The ID of the contest.
            filters: TeamFilters containing search, status, and approval status filters.
            pagination: PaginationParams containing skip and limit values.

        Returns:
            PaginatedResult: Total count and list of ContestTeam objects.
        """
        # Base query
        query = (
            select(ContestTeam)
            .where(ContestTeam.contest_id == contest_id)
        )

        query = self._apply_filters(query, filters)

        # Count query
        count_query = (
            select(func.count(ContestTeam.id))
            .where(ContestTeam.contest_id == contest_id)
        )

        count_query = self._apply_filters(count_query, filters)

        # Execute count
        total_result = await self.db.execute(count_query)
        total = int(total_result.scalar_one())

        # Pagination + eager loading
        query = (
            query.order_by(ContestTeam.enrolled_at.desc(), ContestTeam.id.desc())
            .offset(pagination.skip)
            .limit(pagination.limit)
            .options(
                selectinload(ContestTeam.leader),
                selectinload(ContestTeam.contest_team_member).selectinload(ContestTeamMember.user),
                selectinload(ContestTeam.team).selectinload(Team.members)
            )
        )

        # Execute query
        result = await self.db.execute(query)
        contest_teams = result.scalars().all()

        return PaginatedResult(total=total, items=list(contest_teams))

    def _apply_filters(self, query: Select, filters: TeamFilters):
        if filters.search_term:
            query = query.where(ContestTeam.name.ilike(f"%{filters.search_term}%"))

        if filters.status is not None:
            query = query.where(ContestTeam.team_status.in_(filters.status))

        if filters.approval_status is not None:
            query = query.where(ContestTeam.approval_status == filters.approval_status)

        return query

    async def get_contest_team_members_paginated(
        self,
        contest_team_id: UUID,
        pagination: PaginationParams,
        status: list[ContestTeamMemberStatus] | None = None,
        search_term: str | None = None,
    ) -> PaginatedResult:
        """Retrieve paginated list of contest team members with search and status filters.

        Args:
            contest_team_id: The ID of the contest team.
            pagination: PaginationParams containing skip and limit values.
            status: Optional list of member statuses to filter by.
            search_term: Optional search term for user name or email.

        Returns:
            PaginatedResult: Total count and list of ContestTeamMember objects.
        """
        # Base query
        query = (
            select(ContestTeamMember)
            .join(User, ContestTeamMember.user_id == User.id)
            .where(ContestTeamMember.contest_team_id == contest_team_id)
        )

        # Filters
        if status is not None:
            query = query.where(ContestTeamMember.status.in_(status))

        if search_term:
            query = query.where(
                (User.name.ilike(f"%{search_term}%")) |
                (User.email.ilike(f"%{search_term}%"))
            )

        # Count query
        count_query = (
            select(func.count(ContestTeamMember.id))
            .join(User, ContestTeamMember.user_id == User.id)
            .where(ContestTeamMember.contest_team_id == contest_team_id)
        )
        if status is not None:
            count_query = count_query.where(ContestTeamMember.status.in_(status))
        if search_term:
            count_query = count_query.where(
                (User.name.ilike(f"%{search_term}%")) |
                (User.email.ilike(f"%{search_term}%"))
            )

        # Execute count
        total_result = await self.db.execute(count_query)
        total = int(total_result.scalar_one())

        # Execute paginated query with user loaded
        query = (
            query.order_by(
                case(
                    (ContestTeamMember.status == ContestTeamMemberStatus.ACCEPTED, 1),
                    (ContestTeamMember.status == ContestTeamMemberStatus.INVITED, 2),
                    else_=3
                ),
                ContestTeamMember.id.desc()
            )
            .offset(pagination.skip)
            .limit(pagination.limit)
            .options(selectinload(ContestTeamMember.user))
        )
        result = await self.db.execute(query)
        members = result.scalars().all()

        return PaginatedResult(total=total, items=list(members))
