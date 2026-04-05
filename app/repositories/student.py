"""
Student Repository - Database queries for student operations.

Repository = Data Access Layer
Only this file directly queries the database.
"""

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.contest import Contest, ContestTeam
from app.models.team import Team, TeamUser
from app.repositories.dto.student import PublicContestFilterData


class StudentRepository:
    """
    Repository for student operations.
    
    All database queries go here.
    Service layer calls these methods.
    """

    def __init__(self, db: AsyncSession):
        """
        Args:
            db: Database session (injected by FastAPI)
        """
        self.db = db

    async def get_public_contests(
        self, filters: PublicContestFilterData
    ) -> tuple[int, list[Contest]]:
        """
        Query: Get all PUBLIC contests with filters and pagination.
        
        This is called by SERVICE layer.
        
        Args:
            filters: PublicContestFilterData with search_term, status, skip, limit
            
        Returns:
            (total_count, list_of_contests)
            
        Example:
            filters = PublicContestFilterData(search_term="ICPC", skip=0, limit=10)
            total, contests = await repo.get_public_contests(filters)
            # total = 5
            # contests = [Contest(...), Contest(...), ...]
        """
        # Base query: only PUBLIC contests, not deleted
        query = select(Contest).where(
            Contest.is_public == True,
            Contest.is_deleted == False,
        )

        # Apply search filter if provided
        if filters.search_term:
            search = f"%{filters.search_term}%"
            query = query.where(Contest.name.ilike(search))

        # Apply status filter if provided
        if filters.status:
            query = query.where(Contest.status == filters.status)

        # Get TOTAL count (for pagination)
        count_query = select(Contest).where(
            Contest.is_public == True,
            Contest.is_deleted == False,
        )
        if filters.search_term:
            count_query = count_query.where(
                Contest.name.ilike(f"%{filters.search_term}%")
            )
        if filters.status:
            count_query = count_query.where(Contest.status == filters.status)
        
        count_result = await self.db.execute(count_query)
        total = len(count_result.scalars().all())

        # Apply pagination
        query = query.offset(filters.skip).limit(filters.limit)

        # Execute query
        result = await self.db.execute(query)
        contests = result.scalars().all()

        return total, contests

    async def get_public_contest_by_id(self, contest_id: UUID) -> Contest | None:
        """
        Query: Get a single PUBLIC contest by ID.
        
        Returns None if:
        - Contest not found
        - Contest is PRIVATE (not public)
        - Contest is deleted
        
        Args:
            contest_id: Contest ID
            
        Returns:
            Contest object or None
        """
        query = select(Contest).where(
            Contest.id == contest_id,
            Contest.is_public == True,
            Contest.is_deleted == False,
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_student_registered_contests(
        self, student_id: UUID, skip: int = 0, limit: int = 10
    ) -> tuple[int, list[dict]]:
        """
        Query: Get all contests where THIS student is registered.
        
        This finds all teams the student is in, then gets their contests.
        
        Args:
            student_id: The student's user ID
            skip: Pagination skip
            limit: Pagination limit
            
        Returns:
            (total_count, list_of_contests_with_team_info)
            
        Example return:
            [
                {
                    "contest": Contest(...),
                    "team": Team(...),
                    "team_status": "SUBMITTED"
                }
            ]
        """
        # Query: Contest <- ContestTeam <- Team <- TeamUser (where user = student)
        query = (
            select(Contest, ContestTeam, Team)
            .join(ContestTeam, ContestTeam.contest_id == Contest.id)
            .join(Team, Team.id == ContestTeam.team_id)
            .join(TeamUser, TeamUser.team_id == Team.id)
            .where(
                TeamUser.user_id == student_id,
                Contest.is_deleted == False,
            )
        )

        # Get total count
        count_result = await self.db.execute(query)
        total = len(count_result.all())

        # Apply pagination
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        rows = result.all()

        # Format into dictionaries
        formatted = []
        for contest, contest_team, team in rows:
            formatted.append({
                "contest": contest,
                "team": team,
                "team_status": contest_team.team_status,
            })

        return total, formatted