from typing import List
from app.exceptions.contest import ContestTeamMemberNotFoundException
from app.utils.enums import TeamApprovalStatus
from app.utils.enums import TeamStatus
from sqlalchemy import case, func
from fastapi import param_functions
from app.models import Team
from sqlalchemy.orm import selectinload
from app.exceptions.contest import ContestTeamNotFoundException
from sqlalchemy import select, and_
from uuid import UUID
from app.models import ContestTeamMember
from app.models import ContestTeam
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.enums import ContestTeamMemberStatus
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

    async def get_contest_team_members(self, contest_team_id:UUID, contestTeamMemberStatus: list[ContestTeamMemberStatus] | None = None, user_ids:list[UUID] | None = None )->List[ContestTeamMember]:
        query = (select(ContestTeamMember).where(ContestTeamMember.contest_team_id == contest_team_id))

        if contestTeamMemberStatus is not None:
            query = query.where(ContestTeamMember.status.in_(contestTeamMemberStatus))
        
        if user_ids is not None:
            query = query.where(ContestTeamMember.user_id.in_(user_ids))

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
