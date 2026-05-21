from app.utils.enums import TeamApprovalStatus
from sqlalchemy import or_
from sqlalchemy import exists
from app.models import ContestTeam
from app.utils.enums import ContestTeamMemberStatus
from app.models import ContestTeamMember
from app.models import UserAudience
from sqlalchemy import select
from app.models import ContestAudience
from app.models import Audience
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.contest import Contest
from app.repositories.student.contest import StudentContestRepository
from app.exceptions.contest import (
    StudentNotEligibleForContestError,
    StudentAlreadyInContestError,
    TeamAlreadyInContestError,
)

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
    
    async def check_student_aduiences_for_contest(self,user_ids:list[UUID],contest_id: UUID):

        # extract the audiences for the contest
        contest_audience_subquery = (
            select(ContestAudience.audience_id)
            .where(ContestAudience.contest_id == contest_id)
        )

        eligible_users_query = (
            select(UserAudience.user_id)
            .distinct()
            .where(
                UserAudience.user_id.in_(user_ids),
                UserAudience.audience_id.in_(contest_audience_subquery)
            )
        )

        result = await self.db.execute(eligible_users_query)
        eligible_user_ids = set(result.scalars().all())

        # Check if all users are eligible
        if len(eligible_user_ids) != len(user_ids):
            raise StudentNotEligibleForContestError(user_id=str(list(set(user_ids) - eligible_user_ids)), contest_id=str(contest_id))
            

    async def check_student_already_in_contest(self, contest_id: UUID, user_ids: list[UUID]):

        query = select(ContestTeamMember.user_id).where(
            ContestTeamMember.contest_id == contest_id,
            ContestTeamMember.user_id.in_(user_ids),
            ContestTeamMember.status == ContestTeamMemberStatus.APPROVED
        )

        result = await self.db.execute(query)
        existing_user_ids = set(result.scalars().all())
        if len(existing_user_ids) > 0:
            raise StudentAlreadyInContestError(user_id=str(list(existing_user_ids)), contest_id=str(contest_id))

    async def check_team_already_in_contest(self, team_id: UUID, contest_id: UUID) -> None:
        """Check if a team is already in the contest."""
        query = select(ContestTeam.id).where(
            ContestTeam.contest_id == contest_id,
            ContestTeam.team_id == team_id,
            or_(ContestTeam.approval_status == TeamApprovalStatus.APPROVED, ContestTeam.approval_status == TeamApprovalStatus.WAITING)
        )
        result = await self.db.execute(query)
        if result.scalar_one_or_none() is not None:
            raise TeamAlreadyInContestError(team_id=str(team_id), contest_id=str(contest_id))
    