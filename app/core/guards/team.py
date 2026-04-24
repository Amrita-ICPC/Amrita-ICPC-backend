# app/guards/team_guard.py
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import ContestPermission, TeamPermission
from app.exceptions.auth import PermissionDeniedError
from app.models.audience import UserAudience
from app.models.contest import Contest


class TeamOperationGuard:
    """Guard for team operation permission validation.

    This class implements the Guard Pattern, centralizing all permission checks
    for team-related operations. It ensures users have appropriate permissions
    before allowing operations to proceed.

    Responsibilities:
        - Validate contest management permissions
        - Validate team read/write permissions
        - Check student eligibility for team membership
        - Enforce role-based access control

    Design Principles:
        - Single Responsibility: Only handles permission validation
        - Fail Fast: Raises PermissionDeniedError immediately on failure
        - Centralized Logic: All permission checks in one place
        - Reusable: Called by service layer before operations

    Guard Methods:
        - check_create_team: Validates team creation permissions
        - check_update_team: Validates team modification permissions
        - check_read_team: Validates team read permissions
        - check_add_team_members: Validates member addition permissions
        - check_remove_team_members: Validates member removal permissions

    Exception Strategy:
        - Raises PermissionDeniedError when user lacks permission
        - Provides clear error messages for debugging
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_create_team(
        self,
        user_id: UUID,
        contest: Contest,
        member_ids: list[UUID],
    ):
        """
        Validates:
        - User has contest management permission
        - All members are eligible students for the contest
        """
        await ContestPermission.can_manage_contest(
            self.db, user_id=user_id, contest=contest
        )
        await TeamPermission.is_student_allowed_for_contest(
            self.db, user_ids=member_ids, contest_id=contest.id
        )

    async def check_update_team(
        self,
        user_id: UUID,
        contest: Contest,
    ):
        """
        Validates:
        - User has contest management permission
        """
        await ContestPermission.can_manage_contest(
            self.db, user_id=user_id, contest=contest
        )

    async def check_read_team(
        self,
        user_id: UUID,
        contest: Contest,
    ):
        """
        Validates:
        - User has read permission on the contest
        """
        await ContestPermission.can_read_contest(
            self.db, user_id=user_id, contest=contest
        )

    async def check_add_team_members(
        self,
        user_id: UUID,
        contest: Contest,
        member_ids: list[UUID],
    ):
        """
        Validates:
        - User has contest management permission
        - All new members are eligible students for the contest
        """
        await ContestPermission.can_manage_contest(
            self.db, user_id=user_id, contest=contest
        )
        await TeamPermission.is_student_allowed_for_contest(
            self.db, user_ids=member_ids, contest_id=contest.id
        )

    async def check_remove_team_members(
        self,
        user_id: UUID,
        contest: Contest,
    ):
        """
        Validates:
        - User has contest management permission
        """
        await ContestPermission.can_manage_contest(
            self.db, user_id=user_id, contest=contest
        )

    async def check_create_team_for_student(
        self,
        user_id: UUID,
        contest: Contest,
        member_ids: list[UUID],
    ):
        """
        Validates student self-service team creation.

        For student self-service workflows, only validates student eligibility
        instead of requiring contest management permissions.

        Validates:
        - User is eligible student for the contest
        - All members are eligible students for the contest

        Args:
            user_id: Student user ID creating the team
            contest: Contest ORM object
            member_ids: List of student user IDs to add to team

        Raises:
            PermissionDeniedError: If user or members not eligible for contest
        """
        await TeamPermission.is_student_allowed_for_contest(
            self.db, user_ids=[user_id] + member_ids, contest_id=contest.id
        )

    async def check_user_in_audience(
        self,
        user_id: UUID,
        audience_id: UUID,
    ):
        """
        Validates that a user belongs to a specific audience.

        Args:
            user_id: User to check
            audience_id: Audience to verify membership in

        Raises:
            PermissionDeniedError: If user is not in the audience
        """
        result = await self.db.execute(
            select(UserAudience).where(
                UserAudience.user_id == user_id,
                UserAudience.audience_id == audience_id,
            )
        )
        if result.scalars().first() is None:
            raise PermissionDeniedError(
                f"User {user_id} is not a member of audience {audience_id}"
            )

    async def check_users_in_audience(
        self,
        user_ids: list[UUID],
        audience_id: UUID,
    ):
        """
        Validates that all users belong to a specific audience.

        Args:
            user_ids: Users to check
            audience_id: Audience to verify membership in

        Raises:
            PermissionDeniedError: If any user is not in the audience
        """
        for user_id in user_ids:
            await self.check_user_in_audience(user_id, audience_id)
