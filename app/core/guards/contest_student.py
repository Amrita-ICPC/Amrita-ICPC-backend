from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.contest import (
    StudentAlreadyInContestError,
    StudentNotEligibleForContestError,
    TeamAlreadyInContestError,
)
from app.exceptions.student.contests import NoContestTeamMemberFoundError
from app.models import (
    Audience,
    ContestAudience,
    ContestTeam,
    ContestTeamMember,
    UserAudience,
)
from app.models.contest import Contest
from app.utils.enums import ContestTeamMemberStatus, TeamApprovalStatus, TeamStatus


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

    async def check_student_aduiences_for_contest(self,user_ids:list[UUID],contest_id: UUID) -> None:

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


    async def check_student_already_in_contest(self, contest_id: UUID, user_ids: list[UUID]) -> None:

        query = select(ContestTeamMember.user_id).where(
            ContestTeamMember.contest_id == contest_id,
            ContestTeamMember.user_id.in_(user_ids),
            ContestTeamMember.status == ContestTeamMemberStatus.ACCEPTED
        )

        result = await self.db.execute(query)
        existing_user_ids = set(result.scalars().all())
        if len(existing_user_ids) > 0:
            raise StudentAlreadyInContestError(user_id=str(list(existing_user_ids)), contest_id=str(contest_id))

    async def check_team_already_in_contest(self, team_id: UUID, contest_id: UUID) -> None:
        """Check if a team is already in the contest."""
        query = select(exists().where(
            ContestTeam.contest_id == contest_id,
            ContestTeam.team_id == team_id,
            ContestTeam.approval_status.in_([TeamApprovalStatus.APPROVED, TeamApprovalStatus.WAITING]),
            ContestTeam.team_status.in_([TeamStatus.DRAFT, TeamStatus.CONFIRMED])
        ))
        result = await self.db.scalar(query)
        if result:
            raise TeamAlreadyInContestError(team_id=str(team_id), contest_id=str(contest_id))

    async def check_contest_team_member_exist(self,contest_team_id:UUID, user_id: UUID) -> None:
        query = select(ContestTeamMember.user_id).where(
            ContestTeamMember.contest_team_id == contest_team_id,
            ContestTeamMember.user_id == user_id,
            ContestTeamMember.status == ContestTeamMemberStatus.ACCEPTED
        )

        result = await self.db.execute(query)
        existing_user_ids = set(result.scalars().all())
        if len(existing_user_ids) == 0:
            raise NoContestTeamMemberFoundError(detail=f"User {user_id} is not a member of contest team {contest_team_id}")

