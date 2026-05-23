from app.utils.enums import ContestTeamMemberStatus
from app.models.contest import ContestTeamMember
from app.models import ContestAudience
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Contest, TeamUser, ContestTeam
from sqlalchemy import and_, case, func, or_, select
from app.utils.enums import ContestRunStatus, ContestStatus, TeamApprovalStatus
from uuid import UUID
from app.repositories.dto import PaginationParams
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone
from app.repositories.dto import PaginatedResult
from app.repositories.dto.student.contests import StudentContestFilters

class StudentContestRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_student_contests(
        self,
        user_id: UUID,
        filters: StudentContestFilters,
        pagination: PaginationParams,
    ) -> tuple[PaginatedResult, dict[UUID, int]]:
        """
        Retrieve contests available for a student based on filters.
        Handles visibility (public or user in allowed audience), 
        search, run status, and registration status.
        """
        from app.models.audience import ContestAudience, UserAudience

        # Base query for published contests not deleted
        base_query = (
            select(Contest)
            .options(
                selectinload(Contest.audience_links).joinedload(ContestAudience.audience)
            )
            .filter(
                Contest.is_deleted.is_(False),
                Contest.status == ContestStatus.PUBLISHED,
            )
        )

        # Visibility filter: Public OR (Private AND user in audience)
        user_audiences_query = select(UserAudience.audience_id).filter(
            UserAudience.user_id == user_id
        )
        user_audiences = await self.db.execute(user_audiences_query)
        user_audience_ids = set(user_audiences.scalars().all())

        if user_audience_ids:
            has_audience = select(ContestAudience).filter(
                ContestAudience.contest_id == Contest.id,
                ContestAudience.audience_id.in_(user_audience_ids)
            ).exists()
            
            base_query = base_query.filter(
                or_(
                    Contest.is_public.is_(True),
                    has_audience
                )
            )
        else:
            base_query = base_query.filter(Contest.is_public.is_(True))

        # Search term filter
        if filters.search_term:
            base_query = base_query.filter(
                Contest.name.ilike(f"%{filters.search_term}%")
            )

        # Team size filters
        if filters.min_team_size is not None:
            base_query = base_query.filter(Contest.min_team_size >= filters.min_team_size)
        
        if filters.max_team_size is not None:
            base_query = base_query.filter(Contest.max_team_size <= filters.max_team_size)

        # Run status filter
        now = datetime.now(timezone.utc)
        if filters.run_statuses:
            run_status_conditions = []
            if ContestRunStatus.UPCOMING in filters.run_statuses:
                run_status_conditions.append(Contest.start_time > now)
            if ContestRunStatus.LIVE in filters.run_statuses:
                run_status_conditions.append(
                    and_(Contest.start_time <= now, Contest.end_time >= now)
                )
            if ContestRunStatus.ENDED in filters.run_statuses:
                run_status_conditions.append(Contest.end_time < now)
            
            if run_status_conditions:
                base_query = base_query.filter(or_(*run_status_conditions))

        # Registered filter
        # To filter registered, we need to check if user is in ContestTeam for the contest
        if filters.registered is not None:
            team_user_subquery = (
                select(TeamUser.team_id)
                .filter(TeamUser.user_id == user_id)
            )
            
            registered_condition = select(ContestTeam).filter(
                ContestTeam.contest_id == Contest.id,
                ContestTeam.team_id.in_(team_user_subquery)
            ).exists()
            
            if filters.registered:
                base_query = base_query.filter(registered_condition)
            else:
                base_query = base_query.filter(~registered_condition)


        # Get total count
        count_query = select(func.count()).select_from(
            base_query.with_only_columns(Contest.id).subquery()
        )
        total = (await self.db.execute(count_query)).scalar() or 0

        # Sorting: LIVE -> UPCOMING -> ENDED (then by start_time ascending)
        run_status_order = case(
            (Contest.start_time <= now, case((Contest.end_time >= now, 0), else_=2)),
            else_=1,
        )
        base_query = base_query.order_by(run_status_order, Contest.start_time.asc())

        # Pagination
        result = await self.db.execute(
            base_query.offset(pagination.skip).limit(pagination.limit)
        )
        contests = list(result.unique().scalars().all())
        
        # Calculate registration counts
        contest_ids = [c.id for c in contests]
        teams_count_dict = {}
        
        if contest_ids:
            # Count registered teams
            count_result = await self.db.execute(
                select(ContestTeam.contest_id, func.count(ContestTeam.team_id))
                .filter(
                    ContestTeam.contest_id.in_(contest_ids),
                    ContestTeam.approval_status == TeamApprovalStatus.APPROVED
                )
                .group_by(ContestTeam.contest_id)
            )
            teams_count_dict = {cid: count for cid, count in count_result.all()}

        return PaginatedResult(total=total, items=contests), teams_count_dict  

    async def get_contest_team_member(self, contest_id: UUID, user_id: UUID)->ContestTeamMember | None:
        # Check if the user is in contest_team_member table
        query = select(ContestTeamMember).where(
            ContestTeamMember.contest_id == contest_id,
            ContestTeamMember.user_id == user_id,
            ContestTeamMember.status == ContestTeamMemberStatus.ACCEPTED
        ).options(
            selectinload(ContestTeamMember.contest_team)
            .selectinload(ContestTeam.contest_team_member)
            .selectinload(ContestTeamMember.user),
            selectinload(ContestTeamMember.contest_team)
            .selectinload(ContestTeam.team)
        )
        result = await self.db.execute(query)
        return result.scalars().first()


    # async def get_team_members_in_contest(self, contest_id: UUID, team_id: UUID) -> list[ContestTeamMember]:
    #     """
    #     Retrieve all members of a team for a specific contest.
    #     """
    #     from app.models.user import User
    #     query = (
    #         select(ContestTeamMember)
    #         .options(joinedload(ContestTeamMember.user))
    #         .where(
    #             ContestTeamMember.contest_id == contest_id,
    #             ContestTeamMember.team_id == team_id
    #         )
    #     )
    #     result = await self.db.execute(query)
    #     return list(result.scalars().all())
