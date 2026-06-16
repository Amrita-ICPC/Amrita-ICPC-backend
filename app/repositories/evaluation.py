from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import Evaluation


class EvaluationRepository:
    """Repository for managing evaluation database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_evaluation(self, evaluation: Evaluation) -> Evaluation:
        """Create a new evaluation record in the database.

        Args:
            evaluation: Evaluation ORM model instance.

        Returns:
            The created Evaluation object with ID and timestamps populated.
        """
        self.db.add(evaluation)
        await self.db.flush()
        await self.db.refresh(evaluation)
        return evaluation

    async def get_evaluation(self, evaluation_id: UUID) -> Evaluation | None:
        """Retrieve an evaluation record by its ID.

        Args:
            evaluation_id: UUID of the evaluation to retrieve.

        Returns:
            The Evaluation object if found, or None.
        """
        result = await self.db.execute(
            select(Evaluation).where(Evaluation.id == evaluation_id)
        )
        return result.scalar_one_or_none()

    async def get_active_evaluation(self, contest_id: UUID) -> Evaluation | None:
        """Retrieve the active (not yet fully evaluated) evaluation record for a contest.

        Args:
            contest_id: UUID of the contest.

        Returns:
            The active Evaluation object if found, or None.
        """
        result = await self.db.execute(
            select(Evaluation).where(
                Evaluation.contest_id == contest_id, Evaluation.is_evaluated.is_(False)
            )
        )
        return result.scalar_one_or_none()
