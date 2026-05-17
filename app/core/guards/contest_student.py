from app.models import UserAudience
from sqlalchemy import select
from app.models import ContestAudience
from app.models import Audience
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.contest import Contest
from app.repositories.student.contest import StudentContestRepository
from app.exceptions.contest import StudentNotEligibleForContestError

class ContestStudentGuard:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def check_student_eligibility(self, user_id: UUID, contest: Contest) -> None:
        # check if contest is public
        if contest.is_public:
            return

        query = select(Audience.id).join(UserAudience,UserAudience.audience_id == Audience.id).join(ContestAudience, ContestAudience.audience_id == Audience.id).where(
            UserAudience.user_id == user_id,
            ContestAudience.contest_id == contest.id
        ).limit(1)

        result = await self.db.execute(query)
        if result.fetchone() is None:
            raise StudentNotEligibleForContestError(user_id=str(user_id), contest_id=str(contest.id))
        
        
        
        
        