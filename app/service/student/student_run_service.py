"""Student code run service for testing/executing code against test cases.

This service handles the /run endpoint:
- Student submits code to test
- Service verifies student is in contest
- Calls Judge0Repository to execute code
- Returns result (NOT stored in DB - just for testing)
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.exceptions.auth import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.exceptions.question import QuestionNotFoundError
from app.models.contest import Contest, ContestTeam
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
        # Verify contest exists
        stmt = select(Contest).where(Contest.id == request.contest_id)
        result = await self.db.execute(stmt)
        contest = result.scalars().first()
        
        if not contest:
            raise ContestNotFoundError(str(request.contest_id))
        
        # Verify student is in contest (via team membership)
        # User must be a member of a team that is registered in the contest
        stmt = select(TeamUser).join(ContestTeam).where(
            ContestTeam.contest_id == request.contest_id,
            TeamUser.user_id == request.user_id
        )
        result = await self.db.execute(stmt)
        user_in_contest = result.scalars().first()
        
        if not user_in_contest:
            raise PermissionDeniedError(
                f"User {request.user_id} is not registered in contest {request.contest_id}"
            )
        
        # Verify question exists in contest
        stmt = select(Question).where(
            Question.id == request.question_id,
            Question.bank_id == contest.bank_id  # Question must be from contest's bank
        )
        result = await self.db.execute(stmt)
        question = result.scalars().first()
        
        if not question:
            raise QuestionNotFoundError(str(request.question_id))
        
        # Get test case (use first if not specified)
        if request.testcase_id:
            stmt = select(TestCase).where(
                TestCase.id == request.testcase_id,
                TestCase.question_id == request.question_id
            )
        else:
            # Get first test case for this question
            stmt = select(TestCase).where(
                TestCase.question_id == request.question_id
            ).order_by(TestCase.created_at)
        
        result = await self.db.execute(stmt)
        testcase = result.scalars().first()
        
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
        
        # Check if result passed (Accepted verdict = status 3)
        passed = judge0_result.status_id == 3
        
        # Map Judge0 result to DTO
        run_result = StudentTestCaseRunResultDTO(
            testcase_id=testcase.id,
            passed=passed,
            status_code=judge0_result.status_id,
            status_description=judge0_result.status.name if judge0_result.status else "Unknown",
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

