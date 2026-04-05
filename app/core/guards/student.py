"""
Student Guards - Check permissions and authorization.

Examples:
- Can student view this contest? (Must be public)
- Can student register in this contest? (Already registered? Is contest open?)
"""

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.contest import Contest, ContestTeam
from app.models.team import Team, TeamUser


class StudentOperationGuard:
    """
    Guard for student operations.
    
    Guards check: "Is this user ALLOWED to do this?"
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def can_register_in_contest(
        self, student_id: UUID, contest_id: UUID
    ) -> bool:
        """
        Check if student can register in contest.
        
        Business Rules:
        1. Contest must exist
        2. Contest must be PUBLIC (not private)
        3. Contest must be in SCHEDULED or RUNNING status
        4. Student must NOT already be registered
        
        This gets called in SERVICE layer BEFORE creating team.
        
        Args:
            student_id: Student's user ID
            contest_id: Contest ID they want to register in
            
        Returns:
            True if allowed
            
        Raises:
            ContestNotFoundError: If contest doesn't exist
            PermissionDeniedError: If not allowed for any reason
        """
        # RULE 1: Does contest exist?
        query = select(Contest).where(
            Contest.id == contest_id,
            Contest.is_deleted == False
        )
        result = await self.db.execute(query)
        contest = result.scalar_one_or_none()
        
        if not contest:
            raise ContestNotFoundError(str(contest_id))
        
        # RULE 2: Is contest PUBLIC?
        if not contest.is_public:
            raise PermissionDeniedError(
                "You cannot register in private contests"
            )
        
        # RULE 3: Is contest in valid status?
        from app.utils.enums import ContestStatus
        if contest.status not in [ContestStatus.SCHEDULED, ContestStatus.RUNNING]:
            raise PermissionDeniedError(
                f"Contest is {contest.status.value}. "
                f"Registration only for SCHEDULED or RUNNING contests."
            )
        
        # RULE 4: Is student already registered?
        already_registered = (
            select(ContestTeam)
            .join(Team, Team.id == ContestTeam.team_id)
            .join(TeamUser, TeamUser.team_id == Team.id)
            .where(
                ContestTeam.contest_id == contest_id,
                TeamUser.user_id == student_id,
            )
        )
        result = await self.db.execute(already_registered)
        if result.scalar_one_or_none():
            raise PermissionDeniedError(
                "You are already registered in this contest"
            )
        
        return True