"""TestCase Repository for test case database operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.question import QuestionNotFoundError
from app.models.question import Question, TestCase


class TestCaseRepository:
    """Repository for test case-related database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_non_hidden_by_question(self, question_id: UUID) -> list[TestCase]:
        """Fetch all non-hidden test cases for a question (ordered by position).

        Used for practice runs - only public test cases are returned.
        Non-hidden test cases show correct output for immediate feedback.

        Args:
            question_id: Question ID to fetch test cases for.

        Returns:
            List of TestCase objects (ordered by position) with input/output/weight/order fields.

        Raises:
            QuestionNotFoundError: If question does not exist.
        """
        # First verify question exists
        result = await self.db.execute(
            select(Question.id).where(Question.id == question_id)
        )
        if result.scalar_one_or_none() is None:
            raise QuestionNotFoundError(str(question_id))

        # Fetch non-hidden test cases ordered by position
        result = await self.db.execute(
            select(TestCase)
            .where(TestCase.question_id == question_id, TestCase.is_hidden.is_(False))
            .order_by(TestCase.order)
        )
        return result.scalars().all()

    async def get_all_by_question(self, question_id: UUID) -> list[TestCase]:
        """Fetch all test cases (hidden and visible) for a question.

        Used for internal operations, question editing, and admin views.

        Args:
            question_id: Question ID to fetch test cases for.

        Returns:
            List of all TestCase objects (ordered by position).

        Raises:
            QuestionNotFoundError: If question does not exist.
        """
        # Verify question exists
        result = await self.db.execute(
            select(Question.id).where(Question.id == question_id)
        )
        if result.scalar_one_or_none() is None:
            raise QuestionNotFoundError(str(question_id))

        # Fetch all test cases ordered by position
        result = await self.db.execute(
            select(TestCase)
            .where(TestCase.question_id == question_id)
            .order_by(TestCase.order)
        )
        return result.scalars().all()

    async def get_by_id(self, testcase_id: UUID) -> TestCase | None:
        """Fetch a single test case by ID.

        Args:
            testcase_id: Test case ID to fetch.

        Returns:
            TestCase object if found, None otherwise.
        """
        result = await self.db.execute(
            select(TestCase).where(TestCase.id == testcase_id)
        )
        return result.scalar_one_or_none()

    async def get_by_ids(self, testcase_ids: list[UUID]) -> list[TestCase]:
        """Fetch multiple test cases by IDs.

        Useful for bulk validation and batch operations.

        Args:
            testcase_ids: List of test case IDs to fetch.

        Returns:
            List of TestCase objects (unordered).
        """
        if not testcase_ids:
            return []

        result = await self.db.execute(
            select(TestCase).where(TestCase.id.in_(testcase_ids))
        )
        return result.scalars().all()

    async def create(self, testcase: TestCase) -> TestCase:
        """Create a new test case.

        Args:
            testcase: TestCase object to create.

        Returns:
            The created TestCase object with ID populated.
        """
        self.db.add(testcase)
        await self.db.flush()
        await self.db.refresh(testcase)
        return testcase

    async def bulk_create(self, testcases: list[TestCase]) -> list[TestCase]:
        """Create multiple test cases.

        Args:
            testcases: List of TestCase objects to create.

        Returns:
            List of created TestCase objects with IDs populated.
        """
        if not testcases:
            return []

        self.db.add_all(testcases)
        await self.db.flush()
        return testcases

    async def update(self, testcase: TestCase) -> TestCase:
        """Update an existing test case.

        Args:
            testcase: TestCase object with updated fields.

        Returns:
            The updated TestCase object.
        """
        await self.db.flush()
        await self.db.refresh(testcase)
        return testcase

    async def delete(self, testcase: TestCase) -> None:
        """Delete a test case.

        Args:
            testcase: TestCase object to delete.
        """
        await self.db.delete(testcase)
        await self.db.flush()
