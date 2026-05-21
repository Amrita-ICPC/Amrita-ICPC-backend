from datetime import datetime
from app.utils.enums import (
    InvitationType,
    TeamInvitationStatus,
    TeamMemberRole,
    ContestTeamMemberStatus,
)
from app.models.user import User
from app.models.team import TeamInvitation
from app.models.contest import ContestTeamMember
from app.exceptions.team import (
    StudentTeamNotFoundError,
    StudentTeamInvitationNotFoundError,
    StudentTeamInvitationError,
    StudentTeamUserNotFoundError,
)
from sqlalchemy import delete
from sqlalchemy.orm import aliased
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, exists, case
from sqlalchemy.orm import selectinload

from app.models.team import Team, TeamUser
from app.repositories.dto.pagination import PaginationParams, PaginatedResult
from app.repositories.dto.student.teams import StudentTeamFilters


class StudentTeamRepository:
    def __init__(self, db: AsyncSession) -> None:
        """Initialize the StudentTeamRepository with database session.

        Args:
            db: AsyncSession database connection.
        """
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

        if filters.is_public is not None:
            query = query.where(Team.is_public == filters.is_public)

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

        if filters.is_public is not None:
            count_query = count_query.where(Team.is_public == filters.is_public)

        # Execute count
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Pagination + eager loading
        query = (
            query.order_by(Team.created_at.desc(), Team.id.desc())
            .offset(pagination.skip)
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
        """Create a new team and add the creator as the first member (leader).

        Args:
            team: The Team ORM object to persist.

        Returns:
            Team: The created Team ORM object with loaded relations.
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

    async def delete_student_team(self, team_id: UUID) -> None:
        """Delete a student team and all its user memberships.

        Args:
            team_id: UUID of the team to delete.
        """
        #delete team_users where team_id = team_id
        await self.db.execute(delete(TeamUser).where(TeamUser.team_id == team_id))
        #delete team where id = team_id
        await self.db.execute(delete(Team).where(Team.id == team_id))

        await self.db.flush()

        return 

    async def get_pending_student_invitations_count(
        self, user_id: UUID, invitation_type: InvitationType, team_id: UUID | None
    ) -> int:
        """Get the count of pending invitations or requests.

        Args:
            user_id: UUID of the user.
            invitation_type: The type of invitation (INVITE or REQUEST).
            team_id: Optional team ID to filter by.

        Returns:
            int: The count of pending invitations/requests matching the criteria.
        """
        query = (
            select(func.count(TeamInvitation.id)).where(
                and_(
                    TeamInvitation.invitation_type == invitation_type,
                    TeamInvitation.status == TeamInvitationStatus.PENDING,
                )
            )
        )
        if invitation_type == InvitationType.INVITE:
            query = query.where(TeamInvitation.reciever_id == user_id)
        
        if team_id:
            query = query.where(TeamInvitation.team_id == team_id)
        
        result = await self.db.execute(query)
        return result.scalar_one()

    
    async def get_student_team_invitations(
        self,
        user_id: UUID,
        invitation_type: InvitationType,
        invitation_status: TeamInvitationStatus | None,
        team_id: UUID | None,
        sent: bool = False,
    ) -> list[TeamInvitation]:
        """Retrieve team invitations or requests based on filters.

        Args:
            user_id: UUID of the student user.
            invitation_type: The type of invitation (INVITE or REQUEST).
            invitation_status: Optional TeamInvitationStatus to filter by.
            team_id: Optional team ID to filter by.
            sent: Whether to retrieve sent invitations/requests.

        Returns:
            list[TeamInvitation]: A list of TeamInvitation objects.
        """
        query = select(TeamInvitation).where(TeamInvitation.invitation_type == invitation_type).options(
            selectinload(TeamInvitation.team).selectinload(Team.members),
            selectinload(TeamInvitation.sender),
        )

        if sent:
            query = query.where(TeamInvitation.sender_id == user_id)
        else:
            if invitation_type == InvitationType.INVITE:
                query = query.where(TeamInvitation.reciever_id == user_id)
            elif invitation_type == InvitationType.REQUEST:
                query = query.join(Team, TeamInvitation.team_id == Team.id).where(Team.leader_id == user_id)

        if team_id:
            query = query.where(TeamInvitation.team_id == team_id)

        if invitation_status:
            query = query.where(TeamInvitation.status == invitation_status)

        invitations = await self.db.execute(query)
        return list(invitations.scalars().all())

    async def create_student_team_invitation(
        self,
        team_id: UUID,
        sender_id: UUID,
        invitation_type: InvitationType,
        reciever_id: UUID | None,
    ) -> TeamInvitation:
        """Create a new team invitation or request in the database.

        Args:
            team_id: UUID of the team.
            sender_id: UUID of the user sending the invitation or request.
            invitation_type: The type of invitation (INVITE or REQUEST).
            reciever_id: Optional UUID of the receiving user. Required if type is INVITE.

        Returns:
            TeamInvitation: The created TeamInvitation ORM object with loaded relations.

        Raises:
            StudentTeamInvitationError: If invitation_type is INVITE and reciever_id is None.
        """
        if invitation_type == InvitationType.INVITE and reciever_id is None:
            raise StudentTeamInvitationError("Receiver ID is required for invite invitations")
        
        team_invitation = TeamInvitation(
            team_id = team_id,
            reciever_id = reciever_id,
            sender_id = sender_id,
            invitation_type = invitation_type,
        )
        self.db.add(team_invitation)
        await self.db.flush()

        query = select(TeamInvitation).where(TeamInvitation.id == team_invitation.id).options(
            selectinload(TeamInvitation.team).selectinload(Team.members),
            selectinload(TeamInvitation.sender),
        )

        invitations = await self.db.execute(query)
        return invitations.scalar_one()

    async def get_student_team_invitation_or_raise(self, invitation_id: UUID) -> TeamInvitation:
        """Retrieve a specific team invitation by ID or raise an error if not found.

        Args:
            invitation_id: UUID of the team invitation to retrieve.

        Returns:
            TeamInvitation: The TeamInvitation ORM object if found.

        Raises:
            StudentTeamInvitationNotFoundError: If the invitation does not exist.
        """
        query = select(TeamInvitation).where(TeamInvitation.id == invitation_id).options(
            selectinload(TeamInvitation.team).selectinload(Team.members),
            selectinload(TeamInvitation.sender),
        )
        result = await self.db.execute(query)
        invitation = result.scalar_one_or_none()
        if invitation is None:
            raise StudentTeamInvitationNotFoundError(invitation_id)
        return invitation

    async def update_team_invitation_status(
        self, team_invitation: TeamInvitation, status: TeamInvitationStatus
    ) -> None:
        """Update the status of a team invitation and handle side-effects (e.g., adding user to team).

        If the status is ACCEPTED, the invited user (receiver for INVITE, sender
        for REQUEST) is added to the TeamUser mapping.

        Args:
            team_invitation: The TeamInvitation ORM object.
            status: The new TeamInvitationStatus to set.

        Raises:
            StudentTeamInvitationError: If the receiver ID is missing on acceptance.
        """
        if status == TeamInvitationStatus.ACCEPTED:
            joined_user_id = team_invitation.reciever_id if team_invitation.invitation_type == InvitationType.INVITE else team_invitation.sender_id
            if joined_user_id is None:
                raise StudentTeamInvitationError("Receiver ID is missing from invitation")
            team_user = TeamUser(
                team_id = team_invitation.team_id,
                user_id = joined_user_id,
            )
            team_invitation.status = TeamInvitationStatus.ACCEPTED
            self.db.add(team_user)
            self.db.add(team_invitation)

        elif status == TeamInvitationStatus.REJECTED:
            team_invitation.status = TeamInvitationStatus.REJECTED
            self.db.add(team_invitation)

        elif status == TeamInvitationStatus.CANCELLED:
            team_invitation.status = TeamInvitationStatus.CANCELLED
            self.db.add(team_invitation)

    async def get_team_by_code(self, code: str) -> Team | None:
        """Retrieve a team by its unique 6-digit code.

        Args:
            code: 6-digit team code.

        Returns:
            Team | None: The matched Team or None.
        """
        query = select(Team).where(Team.code == code)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def search_teams_by_name(
        self,
        name_query: str,
        pagination: PaginationParams,
    ) -> PaginatedResult:
        """Search student teams by name or code.

        - If the query is an exact 6-digit number, searches for a public team with that exact code.
        - If no such team exists (or if query is not 6 digits), searches public teams by name.

        Args:
            name_query: Partial team name or exact team code.
            pagination: PaginationParams containing skip and limit.

        Returns:
            PaginatedResult: Total matched count and list of loaded Team models.
        """
        if name_query.isdigit() and len(name_query) == 6:
            # First attempt exact code match (must be public)
            code_filter = and_(Team.code == name_query, Team.is_public == True)
            
            # Count query for code match
            count_query = select(func.count(Team.id)).where(code_filter)
            total_result = await self.db.execute(count_query)
            total = total_result.scalar() or 0
            
            if total > 0:
                # Retrieve the team matching the code
                query = (
                    select(Team)
                    .where(code_filter)
                    .options(
                        selectinload(Team.members).selectinload(TeamUser.user),
                        selectinload(Team.creator),
                        selectinload(Team.leader),
                    )
                )
                result = await self.db.execute(query)
                teams = result.scalars().all()
                return PaginatedResult(total=total, items=list(teams))

        # Fallback to name partial search on public teams
        name_filter = and_(Team.name.ilike(f"%{name_query}%"), Team.is_public == True)

        # Count query
        count_query = select(func.count(Team.id)).where(name_filter)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginated fetch with eager relationship loads
        query = (
            select(Team)
            .where(name_filter)
            .order_by(Team.created_at.desc(), Team.id.desc())
            .offset(pagination.skip)
            .limit(pagination.limit)
            .options(
                selectinload(Team.members).selectinload(TeamUser.user),
                selectinload(Team.creator),
                selectinload(Team.leader),
            )
        )

        result = await self.db.execute(query)
        teams = result.scalars().all()

        return PaginatedResult(total=total, items=list(teams))

    async def get_user_pending_join_requests_data(self, user_id: UUID) -> tuple[set[UUID], int]:
        """Retrieve both the set of team IDs the user requested to join,
        and the count of pending join requests for teams led by the user.

        Args:
            user_id: UUID of the student user.

        Returns:
            tuple[set[UUID], int]: A tuple containing:
                - set[UUID]: Team IDs the user has pending join requests for.
                - int: Count of pending join requests for teams led by the user.
        """
        # Query for team IDs the user has requested to join
        ids_query = select(TeamInvitation.team_id).where(
            and_(
                TeamInvitation.sender_id == user_id,
                TeamInvitation.invitation_type == InvitationType.REQUEST,
                TeamInvitation.status == TeamInvitationStatus.PENDING,
            )
        )
        ids_result = await self.db.execute(ids_query)
        requested_team_ids = set(ids_result.scalars().all())

        # Query for pending request count to teams led by the user
        count_query = (
            select(func.count(TeamInvitation.id))
            .join(Team, TeamInvitation.team_id == Team.id)
            .where(
                and_(
                    TeamInvitation.invitation_type == InvitationType.REQUEST,
                    TeamInvitation.status == TeamInvitationStatus.PENDING,
                    Team.leader_id == user_id,
                )
            )
        )
        count_result = await self.db.execute(count_query)
        requests_count = count_result.scalar_one() or 0

        return requested_team_ids, requests_count

    
    async def leave_team(self,team_id: UUID,user_id:UUID):
        """Remove a user from a team.

        Args:
            team_id: The ID of the team to leave.
            user_id: The ID of the user to remove.
        """
        query = select(TeamUser).where(
            and_(
                TeamUser.team_id == team_id,
                TeamUser.user_id == user_id,
            )
        )
        result = await self.db.execute(query)
        team_user = result.scalar_one_or_none()
        if team_user is None:
            raise StudentTeamUserNotFoundError(team_id, user_id)
        await self.db.delete(team_user)
        await self.db.flush()

    async def get_team_members(
        self,
        team_id: UUID,
        name_filter: str | None = None,
        email_filter: str | None = None,
        joined_after: datetime | None = None,
        joined_before: datetime | None = None,
        sort_by: str = "joined_at",
        order: str = "asc",
        contest_id: UUID | None = None,
    ) -> list[tuple[User, TeamMemberRole, datetime, bool | None]]:
        """Retrieve members of a team with optional filtering and sorting by name, email, and joined_at.

        Args:
            team_id: UUID of the team.
            name_filter: Optional filter for user's name.
            email_filter: Optional filter for user's email.
            joined_after: Optional filter for members joined after this timestamp.
            joined_before: Optional filter for members joined before this timestamp.
            sort_by: Column to sort by ("name", "email", or "joined_at"). Defaults to "joined_at".
            order: Sort order ("asc" or "desc"). Defaults to "asc".
            contest_id: Optional UUID of the contest to check if members are registered in.

        Returns:
            list[tuple[User, TeamMemberRole, datetime, bool | None]]: List of tuples containing the User model,
                their corresponding TeamMemberRole (LEADER or MEMBER), their joined_at timestamp, and whether
                they are already registered in the specified contest (or None if contest_id is not provided).
        """
        query = (
            select(TeamUser, User, Team.leader_id)
            .join(User, TeamUser.user_id == User.id)
            .join(Team, TeamUser.team_id == Team.id)
            .where(TeamUser.team_id == team_id)
        )

        if name_filter:
            query = query.where(User.name.ilike(f"%{name_filter}%"))
        if email_filter:
            query = query.where(User.email.ilike(f"%{email_filter}%"))
        if joined_after:
            query = query.where(TeamUser.joined_at >= joined_after)
        if joined_before:
            query = query.where(TeamUser.joined_at <= joined_before)

        # Ordering / Sorting
        sort_col = TeamUser.joined_at
        if sort_by == "name":
            sort_col = User.name
        elif sort_by == "email":
            sort_col = User.email

        if order.lower() == "desc":
            query = query.order_by(sort_col.desc())
        else:
            query = query.order_by(sort_col.asc())

        result = await self.db.execute(query)
        rows = result.all()

        in_contest_user_ids = set()
        if contest_id and rows:
            user_ids = [user.id for team_user, user, leader_id in rows]
            stmt = select(ContestTeamMember.user_id).where(
                ContestTeamMember.contest_id == contest_id,
                ContestTeamMember.user_id.in_(user_ids),
                ContestTeamMember.status == ContestTeamMemberStatus.APPROVED
            )
            res = await self.db.execute(stmt)
            in_contest_user_ids = set(res.scalars().all())

        members_list = []
        for team_user, user, leader_id in rows:
            team_role = (
                TeamMemberRole.LEADER
                if user.id == leader_id
                else TeamMemberRole.MEMBER
            )
            is_in_contest = user.id in in_contest_user_ids if contest_id else None
            members_list.append((user, team_role, team_user.joined_at, is_in_contest))
        return members_list





        

    
        
        