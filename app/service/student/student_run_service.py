"""Student code run service for testing/executing code against test cases.

This service handles the /run endpoint:
- Student submits code to test
- Service verifies student is in contest
- Calls Judge0Repository to execute code
- Returns result (NOT stored in DB - just for testing)
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.exceptions.auth import PermissionDeniedError
from app.exceptions.question import QuestionNotFoundError
from app.exceptions.student.contests import ContestNotFoundError
from app.models.contest import Contest, ContestQuestion, ContestTeam
from app.models.question import Question, TestCase
from app.models.team import TeamUser
from app.repositories.dto.judge0 import Judge0ExecutionRequestDTO
from app.repositories.dto.student.run import (
    StudentCodeRunRequestDTO,
    StudentCodeRunResponseDTO,
    StudentTestCaseRunResultDTO,
)
from app.repositories.judge0 import Judge0Repository


class StudentRunService:
    """Service for executing student code against test cases.

    Provides quick testing capability for students before official submission.
    Does NOT store execution results in database.
    """

    def __init__(self, db: AsyncSession):
        """Initialize service with database session.

        Args:
            db: SQLAlchemy async database session.
        """
        self.db = db
        self.judge0_repo = Judge0Repository()

    async def run_code(
        self,
        request: StudentCodeRunRequestDTO,
    ) -> StudentCodeRunResponseDTO:
        """Execute student code against a test case.

        Verifies:
        1. Contest exists and is accessible
        2. Student is registered in contest (via team)
        3. Question exists in contest
        4. Test case exists

        Then executes code via Judge0 and returns result.

        Args:
            request: Code execution request with code, language, etc

        Returns:
            StudentCodeRunResponseDTO with execution result

        Raises:
            ContestNotFoundError: If contest doesn't exist
            PermissionDeniedError: If student not in contest
            QuestionNotFoundError: If question doesn't exist
        """
        # 1) Verify contest exists
        contest_stmt = select(Contest).where(Contest.id == request.contest_id)
        contest_result = await self.db.execute(contest_stmt)
        contest = contest_result.scalars().first()
        if not contest:
            raise ContestNotFoundError(str(request.contest_id))

        # 2) Verify student is in contest (via team membership)
        membership_stmt = (
            select(TeamUser)
            .join(ContestTeam, ContestTeam.team_id == TeamUser.team_id)
            .where(
                ContestTeam.contest_id == request.contest_id,
                TeamUser.user_id == request.user_id,
            )
        )
        membership_result = await self.db.execute(membership_stmt)
        user_in_contest = membership_result.scalars().first()
        if not user_in_contest:
            raise PermissionDeniedError(
                f"User {request.user_id} is not registered in contest {request.contest_id}"
            )

        # 3) Verify question exists in contest
        question_stmt = (
            select(Question)
            .join(ContestQuestion, ContestQuestion.question_id == Question.id)
            .where(
                ContestQuestion.contest_id == request.contest_id,
                Question.id == request.question_id,
            )
        )
        question_result = await self.db.execute(question_stmt)
        question = question_result.scalars().first()
        if not question:
            raise QuestionNotFoundError(str(request.question_id))

        # 4) Resolve test case (use first if not specified)
        if request.testcase_id:
            testcase_stmt = select(TestCase).where(
                TestCase.id == request.testcase_id,
                TestCase.question_id == request.question_id,
            )
        else:
            testcase_stmt = (
                select(TestCase)
                .where(TestCase.question_id == request.question_id)
                .order_by(TestCase.created_at)
            )

        testcase_result = await self.db.execute(testcase_stmt)
        testcase = testcase_result.scalars().first()
        if not testcase:
            raise QuestionNotFoundError(
                f"No test case found for question {request.question_id}"
            )

        logger.info(
            f"Running code for user {request.user_id} "
            f"on question {request.question_id} in contest {request.contest_id}"
        )

        # Build Judge0 request DTO
        judge0_request = Judge0ExecutionRequestDTO(
            question_id=str(request.question_id),
            source_code=request.code,
            language_id=request.language_id,
        )

        # Submit code to Judge0
        submission = await self.judge0_repo.submit_code(judge0_request, testcase.input)

        # Wait for execution result
        judge0_result = await self.judge0_repo.wait_for_completion(submission.token)

        status_id = judge0_result.status_id or 0
        passed = status_id == 3

        # Map Judge0 result to DTO
        run_result = StudentTestCaseRunResultDTO(
            testcase_id=testcase.id,
            passed=passed,
            status_code=status_id,
            status_description=judge0_result.status.name
            if judge0_result.status
            else "Unknown",
            time=judge0_result.time or 0.0,
            memory=judge0_result.memory or 0.0,
            stdout=judge0_result.stdout,
            stderr=judge0_result.stderr,
            compile_output=judge0_result.compile_output,
            expected_output=testcase.output,
        )

        response = StudentCodeRunResponseDTO(
            question_id=request.question_id,
            result=run_result,
            message="Code executed successfully",
            passed=passed,
        )

        logger.info(
            f"Code execution complete for user {request.user_id}: "
            f"status={run_result.status_description}, passed={passed}"
        )

        return response
