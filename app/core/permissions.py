from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.auth import PermissionDeniedError
from app.models.contest import Contest, ContestInstructor
from app.models.user import User
from app.utils.enums import UserRole


async def is_admin(db: AsyncSession, user_id: UUID) -> bool:
    """
    Check if the user has admin role.
    """
    return (
        await db.execute(
            select(User.id).filter(User.id == user_id, User.role == UserRole.admin)
        )
    ).first() is not None


class ContestPermission:
    @staticmethod
    async def can_manage_contest(
        db: AsyncSession,
        *,
        user_id: UUID,
        contest: Contest,
    ) -> None:
        """
        Raises PermissionDeniedError if user cannot manage contest.
        """

        # creator always allowed
        if contest.created_by == user_id:
            return

        if await is_admin(db, user_id):
            return

        # instructor allowed
        is_instructor = (
            await db.execute(
                select(ContestInstructor).filter(
                    ContestInstructor.contest_id == contest.id,
                    ContestInstructor.instructor_id == user_id,
                )
            )
        ).first() is not None

        if is_instructor:
            return

        raise PermissionDeniedError("You do not have permission to manage this contest")

    @staticmethod
    async def can_read_contest(
        db: AsyncSession,
        *,
        user_id: UUID,
        contest: Contest,
    ) -> None:
        """
        Raises PermissionDeniedError if user cannot read contest.
        """
        # Public contests are readable by everyone
        if contest.is_public:
            return

        # Creator always allowed
        if contest.created_by == user_id:
            return

        # Admins allowed
        if await is_admin(db, user_id):
            return

        # Instructors allowed
        is_instructor = (
            await db.execute(
                select(ContestInstructor).filter(
                    ContestInstructor.contest_id == contest.id,
                    ContestInstructor.instructor_id == user_id,
                )
            )
        ).first() is not None
        if is_instructor:
            return

        # TODO: checking participation (TeamUser)
        # For now, we restrict private contests to managers.
        # If participants need access, we should query ContestTeam -> Team -> TeamUser.

        raise PermissionDeniedError("You do not have permission to view this contest")


class TeamPermission:
    @staticmethod
    async def is_student_allowed_for_contest(
        db: AsyncSession,
        *,
        user_ids: list[UUID],
        contest_id: UUID,
    ) -> None:
        """
        Raises PermissionDeniedError if user is already in a team for the contest.
        """
        from app.models.contest import ContestTeam
        from app.models.team import TeamUser

        # Check if user is already in a team for this contest
        existing_participation = (
            await db.execute(
                select(TeamUser.user_id)
                .join(ContestTeam, ContestTeam.team_id == TeamUser.team_id)
                .filter(
                    ContestTeam.contest_id == contest_id,
                    TeamUser.user_id.in_(user_ids),
                )
            )
        ).first()

        if existing_participation:
            raise PermissionDeniedError(
                f"User {existing_participation} is already a member of a team in this contest"
            )

    @staticmethod
    async def can_update_team(
        db: AsyncSession,
        *,
        user_id: UUID,
        contest: Contest,
        team_leader_id: UUID,
    ) -> None:
        """
        Raises PermissionDeniedError if user cannot update team.
        - User must have contest management permission (creator/instructor/admin)
          OR be the team leader.
        """
        if user_id == team_leader_id:
            return
        await ContestPermission.can_manage_contest(db, user_id=user_id, contest=contest)
