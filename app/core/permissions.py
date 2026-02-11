from uuid import UUID

from sqlalchemy.orm import Session

from app.exceptions.auth import PermissionDeniedError
from app.models.contest import Contest, ContestInstructor
from app.models.user import User
from app.utils.enums import UserRole


class ContestPermission:
    @staticmethod
    def can_manage_contest(
        db: Session,
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

        # admin allowed
        is_admin = (
            db.query(User.id)
            .filter(User.id == user_id, User.role == UserRole.admin)
            .first()
            is not None
        )

        if is_admin:
            return

        # instructor allowed
        is_instructor = (
            db.query(ContestInstructor)
            .filter(
                ContestInstructor.contest_id == contest.id,
                ContestInstructor.instructor_id == user_id,
            )
            .first()
            is not None
        )

        if is_instructor:
            return

        raise PermissionDeniedError("You do not have permission to manage this contest")
