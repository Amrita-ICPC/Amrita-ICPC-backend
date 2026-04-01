from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import is_admin
from app.exceptions.question import QuestionPermissionError
from app.models.question import Question


class QuestionOperationGuard:
    """Guard for question operation permission validation."""

    def __init__(self, db: AsyncSession, repository=None):
        self.db = db
        self.repository = repository

    async def check_manage_question(self, user_id: UUID, question: Question) -> None:
        """
        Validates that the user has permission to manage (update/delete) the question.

        Args:
            user_id: ID of the user attempting the operation
            question: Question object being managed

        Raises:
            QuestionPermissionError: If user lacks management permission
        """
        if question.created_by == user_id:
            return

        if await is_admin(self.db, user_id):
            return

        # Additional logic (e.g. if question belongs to a bank and we manage the bank)
        # would go here. For now, we only check creator and admin.
        raise QuestionPermissionError(
            "You do not have permission to manage this question"
        )

    async def check_read_question(self, user_id: UUID, question: Question) -> None:
        """
        Validates that the user has permission to read the question.

        Args:
            user_id: ID of the user attempting to read
            question: Question object being read

        Raises:
            QuestionPermissionError: If user lacks read permission
        """
        # Creator
        if question.created_by == user_id:
            return

        # Admin
        if await is_admin(self.db, user_id):
            return

        # Bank access
        if self.repository:
            has_bank_access = (
                await self.repository.user_has_access_to_question_via_bank(
                    user_id, question.id
                )
            )
            if has_bank_access:
                return

            # Contest access
            has_contest_access = (
                await self.repository.user_has_access_to_question_via_contest(
                    user_id, question.id
                )
            )
            if has_contest_access:
                return

        raise QuestionPermissionError(
            "You do not have permission to read this question"
        )
