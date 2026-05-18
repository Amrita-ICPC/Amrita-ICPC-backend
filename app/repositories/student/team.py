from app.utils.enums import TeamInvitationStatus
from app.models.team import TeamInvitation
from app.exceptions.team import StudentTeamNotFoundError, StudentTeamInvitationNotFoundError
from sqlalchemy import delete
from sqlalchemy.orm import aliased
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, exists, case
from sqlalchemy.orm import selectinload

from app.models.team import Team, TeamUser
from app.repositories.dto.pagination import PaginationParams, PaginatedResult
from app.repositories.dto.student.teams import StudentTeamFilters


class StudentTeamRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_student_teams(
        self,
        user_id: UUID,
        filters: StudentTeamFilters,
        pagination: PaginationParams,
    ) -> PaginatedResult:
        """Retrieve paginated and filtered list of teams for a student.

        Args:
            user_id: UUID of the requesting student user.
            filters: StudentTeamFilters containing search, creation, and size parameters.
            pagination: PaginationParams containing skip and limit values.

        Returns:
            PaginatedResult: Total count and list of Team objects matching the criteria.
        """
        # Subquery for team member counts
        size_subquery = (
            select(
                TeamUser.team_id,
                func.count(TeamUser.user_id).label("member_count"),
            )
            .group_by(TeamUser.team_id)
            .subquery()
        )

        # Base query
        query = (
            select(Team)
            .join(size_subquery, Team.id == size_subquery.c.team_id)
            .where(
                exists().where(
                    and_(
                        TeamUser.team_id == Team.id,
                        TeamUser.user_id == user_id,
                    )
                )
            )
        )

        # Filters
        if filters.search_term:
            query = query.where(Team.name.ilike(f"%{filters.search_term}%"))

        if filters.created_only:
            query = query.where(Team.created_by == user_id)

        if filters.leader_only:
            query = query.where(Team.leader_id == user_id)

        if filters.min_size is not None:
            query = query.where(size_subquery.c.member_count >= filters.min_size)

        if filters.max_size is not None:
            query = query.where(size_subquery.c.member_count <= filters.max_size)

        # Count query
        count_query = (
            select(func.count())
            .select_from(Team)
            .join(size_subquery, Team.id == size_subquery.c.team_id)
            .where(
                exists().where(
                    and_(
                        TeamUser.team_id == Team.id,
                        TeamUser.user_id == user_id,
                    )
                )
            )
        )

        # Apply same filters to count query
        if filters.search_term:
            count_query = count_query.where(Team.name.ilike(f"%{filters.search_term}%"))

        if filters.created_only:
            count_query = count_query.where(Team.created_by == user_id)

        if filters.leader_only:
            count_query = count_query.where(Team.leader_id == user_id)

        if filters.min_size is not None:
            count_query = count_query.where(size_subquery.c.member_count >= filters.min_size)

        if filters.max_size is not None:
            count_query = count_query.where(size_subquery.c.member_count <= filters.max_size)

        # Execute count
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Pagination + eager loading
        query = (
            query.offset(pagination.skip)
            .limit(pagination.limit)
            .options(
                selectinload(Team.members).selectinload(TeamUser.user),
                selectinload(Team.creator),
                selectinload(Team.leader),
            )
        )

        # Execute main query
        result = await self.db.execute(query)
        teams = result.scalars().all()

        return PaginatedResult(total=total, items=list(teams))

    async def get_student_team_by_id_or_raise(self, user_id: UUID, team_id: UUID) -> Team:
        """Retrieve a specific team by its ID, ensuring the student is a member of the team.

        Args:
            user_id: UUID of the requesting student user.
            team_id: UUID of the team to retrieve.

        Returns:
            Team: The Team ORM object if found and accessible.

        Raises:
            StudentTeamNotFoundError: If the team is not found or the student is not a member.
        """
        query = select(Team).filter(
            and_(
                Team.id == team_id,
                exists().where(
                    and_(
                        TeamUser.team_id == Team.id,
                        TeamUser.user_id == user_id,
                    )
                ),
            )
        )
        # Eager load relationships for mapping optimization
        query = query.options(
            selectinload(Team.members).selectinload(TeamUser.user),
            selectinload(Team.creator),
            selectinload(Team.leader),
        )
        result = await self.db.execute(query)
        team = result.scalar_one_or_none()

        if team is None:
            raise StudentTeamNotFoundError(team_id)
        
        return team

    async def create_student_team(self, team: Team) -> Team:
        """Create a new team.

        Args:
            team: Team ORM database model.

        Returns:
            Team: The created Team ORM object.
        """
        self.db.add(team)
        team_user = TeamUser(
            team=team,
            user_id = team.leader_id,
        )
        self.db.add(team_user)
        await self.db.flush()        

        query = (
        select(Team)
        .where(Team.id == team.id)
        .options(
            selectinload(Team.members).selectinload(TeamUser.user),
            selectinload(Team.creator),
            selectinload(Team.leader),
        )
    )
        result = await self.db.execute(query)
        return result.scalar_one()

    async def update_student_team(self, team: Team) -> Team:
        """Update an existing team's attributes in the database.

        Args:
            team: The Team ORM object with updated fields.

        Returns:
            Team: The updated and refreshed Team ORM object.
        """
        self.db.add(team)
        await self.db.flush()

        # Fetch and return the fully refreshed Team object with eager loaded relationships
        query = (
            select(Team)
            .where(Team.id == team.id)
            .options(
                selectinload(Team.members).selectinload(TeamUser.user),
                selectinload(Team.creator),
                selectinload(Team.leader),
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one()

    async def delete_student_team(self,team_id: UUID):
        #delete team_users where team_id = team_id
        await self.db.execute(delete(TeamUser).where(TeamUser.team_id == team_id))
        #delete team where id = team_id
        await self.db.execute(delete(Team).where(Team.id == team_id))

        await self.db.commit()

        return 

    async def get_pending_student_invitations_count(self,user_id)->int:
        query = select(func.count()).where(TeamInvitation.user_id == user_id, TeamInvitation.status == TeamInvitationStatus.PENDING)
        result = await self.db.execute(query)
        return result.scalar_one()

    
    async def get_student_team_invitations(self, user_id: UUID, invitation_status: TeamInvitationStatus | None):
        query = select(TeamInvitation).where(TeamInvitation.user_id == user_id).options(
            selectinload(TeamInvitation.team).selectinload(Team.members),
            selectinload(TeamInvitation.invited_by_user),
        )

        if invitation_status:
            query = query.where(TeamInvitation.status == invitation_status)

        invitations = await self.db.execute(query)
        return invitations.scalars().all()

    async def create_student_team_invitation(self, team_id:UUID, user_id:UUID, invited_by_id:UUID) -> TeamInvitation:
        team_invitation = TeamInvitation(
            team_id = team_id,
            user_id = user_id,
            invited_by = invited_by_id,
        )
        self.db.add(team_invitation)
        await self.db.commit()

        query = select(TeamInvitation).where(TeamInvitation.id == team_invitation.id).options(
            selectinload(TeamInvitation.team).selectinload(Team.members),
            selectinload(TeamInvitation.invited_by_user),
        )

        invitations = await self.db.execute(query)
        return invitations.scalar_one()

    async def get_student_team_invitation_or_raise(self, user_id: UUID, invitation_id: UUID)->TeamInvitation:
        query = select(TeamInvitation).where(TeamInvitation.user_id == user_id, TeamInvitation.id == invitation_id).options(
            selectinload(TeamInvitation.team).selectinload(Team.members),
            selectinload(TeamInvitation.invited_by_user),
        )
        result = await self.db.execute(query)
        invitation = result.scalar_one_or_none()
        if invitation is None:
            raise StudentTeamInvitationNotFoundError(invitation_id)
        return invitation

    async def approve_or_reject_team_invitation(self, team_invitation: TeamInvitation, status: TeamInvitationStatus):
        if status == TeamInvitationStatus.ACCEPTED:
            team_user = TeamUser(
                team_id = team_invitation.team_id,
                user_id = team_invitation.user_id,
            )
            team_invitation.status = TeamInvitationStatus.ACCEPTED
            self.db.add(team_user)
            self.db.add(team_invitation)

        elif status == TeamInvitationStatus.REJECTED:
            team_invitation.status = TeamInvitationStatus.REJECTED
            self.db.add(team_invitation)

        

    
        
        