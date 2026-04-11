"""Student code run service for testing/executing code against test cases.

This service handles the /run endpoint:
- Student submits code to test
- Service verifies student is in contest
- Calls Judge0 to execute code
- Returns result (NOT stored in DB - just for testing)
"""

from uuid import UUID
from sqlalchemy.orm import Session

from app.core.clients.judge0 import Judge0Client
from app.core.logger import logger
from app.exceptions.auth import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.exceptions.question import QuestionNotFoundError
from app.models.contest import Contest, ContestTeam, ContestTeamUser
from app.models.question import Question, TestCase
from app.repositories.dto.student.run import (
    StudentCodeRunRequestDTO,
    StudentCodeRunResponseDTO,
    StudentTestCaseRunResultDTO,
)


class StudentRunService:
    """Service for executing student code against test cases.
    
    Provides quick testing capability for students before official submission.
    Does NOT store execution results in database.
    """

    def __init__(self, db: Session):
        """Initialize service with database session.
        
        Args:
            db: SQLAlchemy database session.
        """
        self.db = db
        self.judge0_client = Judge0Client()

    def run_code(
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
        contest = self.db.query(Contest).filter(
            Contest.id == request.contest_id
        ).first()
        
        if not contest:
            raise ContestNotFoundError(str(request.contest_id))
        
        # Verify student is in contest (via team registration)
        user_in_contest = self.db.query(ContestTeamUser).join(
            ContestTeam
        ).filter(
            ContestTeam.contest_id == request.contest_id,
            ContestTeamUser.user_id == request.user_id
        ).first()
        
        if not user_in_contest:
            raise PermissionDeniedError(
                f"User {request.user_id} is not registered in contest {request.contest_id}"
            )
        
        # Verify question exists in contest
        question = self.db.query(Question).filter(
            Question.id == request.question_id,
            Question.bank_id == contest.bank_id  # Question must be from contest's bank
        ).first()
        
        if not question:
            raise QuestionNotFoundError(str(request.question_id))
        
        # Get test case (use first if not specified)
        if request.testcase_id:
            testcase = self.db.query(TestCase).filter(
                TestCase.id == request.testcase_id,
                TestCase.question_id == request.question_id
            ).first()
        else:
            # Get first test case for this question
            testcase = self.db.query(TestCase).filter(
                TestCase.question_id == request.question_id
            ).order_by(TestCase.created_at).first()
        
        if not testcase:
            raise QuestionNotFoundError(
                f"No test case found for question {request.question_id}"
            )
        
        logger.info(
            f"Running code for user {request.user_id} "
            f"on question {request.question_id} in contest {request.contest_id}"
        )
        
        # Execute code via Judge0
        result = self.judge0_client.execute_code(
            code=request.code,
            language_id=request.language_id,
            stdin=testcase.input_data,
            expected_output=testcase.expected_output,
        )
        
        # Map Judge0 result to DTO
        run_result = StudentTestCaseRunResultDTO(
            testcase_id=testcase.id,
            passed=result.passed,
            status_code=result.status_code,
            status_description=result.status_description,
            time=result.time,
            memory=result.memory,
            stdout=result.stdout,
            stderr=result.stderr,
            compile_output=result.compile_output,
            expected_output=testcase.expected_output,
        )
        
        response = StudentCodeRunResponseDTO(
            question_id=request.question_id,
            result=run_result,
            message="Code executed successfully",
            passed=run_result.passed,
        )
        
        logger.info(
            f"Code execution complete for user {request.user_id}: "
            f"status={run_result.status_description}, passed={run_result.passed}"
        )
        
        return response
