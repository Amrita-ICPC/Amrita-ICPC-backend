from datetime import datetime, timezone

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, NoResultFound, SQLAlchemyError

from app.core.logger import logger
from app.exceptions.bank_validation import BankValidationError
from app.exceptions.base import AppBaseException
from app.exceptions.contest import (
    ContestAlreadyExistsError,
    ContestNotFoundError,
    ContestOperationError,
    DuplicateQuestionOrderError,
    InstructorAlreadyAssignedError,
    InstructorNotAssignedError,
    InstructorNotFoundError,
    InvalidContestError,
    InvalidContestQuestionDataError,
    QuestionAlreadyInContestError,
    QuestionNotInContestError,
)
from app.exceptions.execution import (
    CodeExecutionError,
    CompilationError,
    InvalidCodeError,
    InvalidLanguageError,
    InvalidSubmissionTokenError,
    NoTestCasesError,
)
from app.exceptions.judge0 import Judge0NotInitializedError
from app.exceptions.question import QuestionNotFoundError, TemplateAlreadyExistsError
from app.exceptions.team import (
    TeamNotFoundError,
)
from app.schema.base import APIErrorResponse, ErrorDetails, MetaResponse
from app.schema.execution import CompilationErrorResponse


def _create_error_response(
    request: Request,
    status_code: int,
    message: str,
    error_code: str,
    details: list[str] | list[dict] | None = None,
) -> JSONResponse:
    meta = MetaResponse(
        request_id=getattr(request.state, "request_id", "unknown"),
        timestamp=datetime.now(timezone.utc),
    )

    error_response = APIErrorResponse(
        success=False,
        status=status_code,
        message=message,
        error=ErrorDetails(code=error_code, details=details),
        meta=meta,
    )

    return JSONResponse(
        status_code=status_code,
        content=error_response.model_dump(mode="json"),
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers for the FastAPI application."""

    @app.exception_handler(AppBaseException)
    async def app_exception_handler(request: Request, exc: AppBaseException):
        logger.warning(f"App exception: {exc.message} (Status: {exc.status_code})")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code=exc.__class__.__name__,
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        logger.error(f"Validation error: {exc}")
        errors = exc.errors()
        # Sanitize errors to ensure JSON serializability
        sanitized_errors = []
        for error in errors:
            sanitized_error = error.copy()
            if "ctx" in sanitized_error:
                # Remove or convert non-serializable objects in ctx
                # For example, ValueError is not serializable
                ctx = sanitized_error["ctx"]
                new_ctx = {}
                for k, v in ctx.items():
                    if isinstance(v, Exception):
                        new_ctx[k] = str(v)
                    else:
                        new_ctx[k] = v
                sanitized_error["ctx"] = new_ctx
            sanitized_errors.append(sanitized_error)

        return _create_error_response(
            request=request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message="Validation error",
            error_code="VALIDATION_ERROR",
            details=sanitized_errors,
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
        logger.error(f"Database error: {str(exc)}")
        return _create_error_response(
            request=request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="A database error occurred",
            error_code="DATABASE_ERROR",
            details=["Internal server error"],
        )

    @app.exception_handler(IntegrityError)
    async def integrity_exception_handler(request: Request, exc: IntegrityError):
        logger.error(f"Integrity error: {str(exc)}")
        return _create_error_response(
            request=request,
            status_code=status.HTTP_409_CONFLICT,
            message="Data integrity violation (e.g., duplicate entry)",
            error_code="INTEGRITY_ERROR",
            details=["Conflict"],
        )

    @app.exception_handler(NoResultFound)
    async def no_result_exception_handler(request: Request, exc: NoResultFound):
        logger.warning(f"No result found: {str(exc)}")
        return _create_error_response(
            request=request,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Requested resource not found",
            error_code="NOT_FOUND",
            details=["Resource not found"],
        )

    @app.exception_handler(ContestNotFoundError)
    async def contest_not_found_handler(request: Request, exc: ContestNotFoundError):
        logger.warning(f"Contest not found: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="CONTEST_NOT_FOUND",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(ContestAlreadyExistsError)
    async def contest_already_exists_handler(
        request: Request, exc: ContestAlreadyExistsError
    ):
        logger.warning(f"Contest already exists: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="CONTEST_ALREADY_EXISTS",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(BankValidationError)
    async def bank_validation_error_handler(request: Request, exc: BankValidationError):
        logger.warning(f"Bank validation failed: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="BANK_VALIDATION_ERROR",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(InvalidContestError)
    async def invalid_contest_handler(request: Request, exc: InvalidContestError):
        logger.warning(f"Invalid contest data: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="INVALID_CONTEST",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(QuestionAlreadyInContestError)
    async def question_already_in_contest_handler(
        request: Request, exc: QuestionAlreadyInContestError
    ):
        logger.warning(f"Question already in contest: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="QUESTION_ALREADY_IN_CONTEST",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(QuestionNotInContestError)
    async def question_not_in_contest_handler(
        request: Request, exc: QuestionNotInContestError
    ):
        logger.warning(f"Question not in contest: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="QUESTION_NOT_IN_CONTEST",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(InvalidContestQuestionDataError)
    async def invalid_contest_question_data_handler(
        request: Request, exc: InvalidContestQuestionDataError
    ):
        logger.warning(f"Invalid contest question data: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="INVALID_CONTEST_QUESTION_DATA",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(DuplicateQuestionOrderError)
    async def duplicate_question_order_handler(
        request: Request, exc: DuplicateQuestionOrderError
    ):
        logger.warning(f"Duplicate question order: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="DUPLICATE_QUESTION_ORDER",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(ContestOperationError)
    async def contest_operation_error_handler(
        request: Request, exc: ContestOperationError
    ):
        logger.error(f"Contest operation error: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="CONTEST_OPERATION_ERROR",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(InstructorAlreadyAssignedError)
    async def instructor_already_assigned_handler(
        request: Request, exc: InstructorAlreadyAssignedError
    ):
        logger.warning(f"Instructor already assigned: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="INSTRUCTOR_ALREADY_ASSIGNED",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(InstructorNotAssignedError)
    async def instructor_not_assigned_handler(
        request: Request, exc: InstructorNotAssignedError
    ):
        logger.warning(f"Instructor not assigned: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="INSTRUCTOR_NOT_ASSIGNED",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(InstructorNotFoundError)
    async def instructor_not_found_handler(
        request: Request, exc: InstructorNotFoundError
    ):
        logger.warning(f"Instructor not found: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="INSTRUCTOR_NOT_FOUND",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(TeamNotFoundError)
    async def team_not_found_handler(request: Request, exc: TeamNotFoundError):
        logger.warning(f"Team not found: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="TEAM_NOT_FOUND",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(QuestionNotFoundError)
    async def question_not_found_handler(request: Request, exc: QuestionNotFoundError):
        logger.warning(f"Question not found: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="QUESTION_NOT_FOUND",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(TemplateAlreadyExistsError)
    async def template_already_exists_handler(
        request: Request, exc: TemplateAlreadyExistsError
    ):
        logger.warning(f"Template already exists: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="TEMPLATE_ALREADY_EXISTS",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(InvalidCodeError)
    async def invalid_code_error_handler(request: Request, exc: InvalidCodeError):
        logger.warning(f"Invalid code error: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="INVALID_CODE",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(InvalidLanguageError)
    async def invalid_language_error_handler(
        request: Request, exc: InvalidLanguageError
    ):
        logger.warning(f"Invalid language error: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="INVALID_LANGUAGE",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(InvalidSubmissionTokenError)
    async def invalid_submission_token_handler(
        request: Request, exc: InvalidSubmissionTokenError
    ):
        logger.warning(f"Invalid submission token: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="INVALID_SUBMISSION_TOKEN",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(CodeExecutionError)
    async def code_execution_error_handler(request: Request, exc: CodeExecutionError):
        logger.error(f"Code execution error: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="CODE_EXECUTION_ERROR",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(Judge0NotInitializedError)
    async def judge0_not_initialized_handler(
        request: Request, exc: Judge0NotInitializedError
    ):
        logger.error(f"Judge0 not initialized: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="JUDGE0_NOT_INITIALIZED",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(NoTestCasesError)
    async def no_test_cases_error_handler(request: Request, exc: NoTestCasesError):
        logger.warning(f"No test cases error: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="NO_TEST_CASES",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(CompilationError)
    async def compilation_error_handler(request: Request, exc: CompilationError):
        logger.warning(f"Compilation error: {exc.message}")
        # Return CompilationErrorResponse with HTTP 400
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=CompilationErrorResponse(
                error_code="COMPILATION_ERROR",
                compile_output=exc.compile_output,
                message=exc.message,
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
        return _create_error_response(
            request=request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="An unexpected error occurred",
            error_code="INTERNAL_SERVER_ERROR",
            details=["Internal server error"],
        )
