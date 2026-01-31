from uuid import UUID
from sqlalchemy.orm import Session

from app.exceptions.auth import PermissionDeniedError
from app.models.contest import Contest, ContestInstructor


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
