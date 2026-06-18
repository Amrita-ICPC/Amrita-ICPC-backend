from datetime import datetime, timezone

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, NoResultFound, SQLAlchemyError

from app.core.logger import logger
from app.exceptions.audience import (
    UserNotInAudienceError,
)
from app.exceptions.bank import (
    BankAccessDeniedError,
    BankAlreadyExistsError,
    BankNotFoundError,
    BankOwnerUnshareError,
    BankPermissionError,
)
from app.exceptions.bank_validation import BankValidationError
from app.exceptions.base import AppBaseException
from app.exceptions.contest import (
    AccessDeniedTeamStatusError,
    AudienceNotAssignedToContestError,
    ContestAlreadyExistsError,
    ContestMaxTeamsReachedError,
    ContestNotFoundError,
    ContestOperationError,
    ContestTeamMemberNotFoundException,
    ContestTeamNotFoundException,
    ContestTeamProgressNotFoundError,
    DuplicateQuestionOrderError,
    InstructorAlreadyAssignedError,
    InstructorNotAssignedError,
    InstructorNotFoundError,
    InvalidContestError,
    InvalidContestQuestionDataError,
    InvalidContestStateError,
    QuestionAlreadyInContestError,
    QuestionNotInContestError,
    StudentAlreadyInContestError,
    StudentContestSessionAlreadyStartedError,
    StudentNotEligibleForContestError,
    TeamAlreadyInContestError,
    TeamDisqualifiedError,
)
from app.exceptions.execution import (
    CodeExecutionError,
    CompilationError,
    InvalidCodeError,
    InvalidLanguageError,
    InvalidSubmissionTokenError,
    NoTestCasesError,
)
from app.exceptions.image import (
    ImageNotFoundError,
    ImageStorageError,
    InvalidImageDataError,
    InvalidImagePathError,
)
from app.exceptions.judge0 import Judge0NotInitializedError
from app.exceptions.question import (
    QuestionNotFoundError,
    TagAlreadyExistsError,
    TagNotFoundError,
    TemplateAlreadyExistsError,
)
from app.exceptions.student.contests import NoContestTeamMemberFoundError
from app.exceptions.student.teams import (
    InvalidContestTeamMemberStatusUpdateException,
    TeamStatusNotAllowedForUpdatingContestTeamMemberStatusException,
)
from app.exceptions.team import (
    IndividualModeActionNotAllowedError,
    LeaderMustBeMemberError,
    StudentTeamInvitationError,
    StudentTeamInvitationNotFoundError,
    StudentTeamUserNotFoundError,
    TeamIsConfirmedError,
    TeamNotFoundError,
    TeamNotHavingRequiredNumberOfMembersException,
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

    @app.exception_handler(NoContestTeamMemberFoundError)
    async def no_contest_team_member_found_handler(
        request: Request, exc: NoContestTeamMemberFoundError
    ):
        logger.warning(f"No contest team member found: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="NO_CONTEST_TEAM_MEMBER_FOUND",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(AudienceNotAssignedToContestError)
    async def audience_not_assigned_to_contest_handler(
        request: Request, exc: AudienceNotAssignedToContestError
    ):
        logger.warning(f"Audience not assigned to contest: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="AUDIENCE_NOT_ASSIGNED_TO_CONTEST",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(UserNotInAudienceError)
    async def user_not_in_audience_handler(
        request: Request, exc: UserNotInAudienceError
    ):
        logger.warning(f"User not in audience: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="USER_NOT_IN_AUDIENCE",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(StudentNotEligibleForContestError)
    async def student_not_eligible_for_contest_handler(
        request: Request, exc: StudentNotEligibleForContestError
    ):
        logger.warning(f"Student not eligible for contest: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="STUDENT_NOT_ELIGIBLE_FOR_CONTEST",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(ContestTeamNotFoundException)
    async def contest_team_not_found_handler(
        request: Request, exc: ContestTeamNotFoundException
    ):
        logger.warning(f"Contest team not found: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="CONTEST_TEAM_NOT_FOUND",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(StudentAlreadyInContestError)
    async def student_already_in_contest_handler(
        request: Request, exc: StudentAlreadyInContestError
    ):
        logger.warning(f"Student already in contest: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="STUDENT_ALREADY_IN_CONTEST",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(StudentContestSessionAlreadyStartedError)
    async def student_contest_session_already_started_handler(
        request: Request, exc: StudentContestSessionAlreadyStartedError
    ):
        logger.warning(f"Student contest session already started: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="STUDENT_CONTEST_SESSION_ALREADY_STARTED",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(AccessDeniedTeamStatusError)
    async def access_denied_team_status_handler(
        request: Request, exc: AccessDeniedTeamStatusError
    ):
        logger.warning(f"Access denied team status: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="ACCESS_DENIED_TEAM_STATUS",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(ContestTeamMemberNotFoundException)
    async def contest_team_member_not_found_handler(
        request: Request, exc: ContestTeamMemberNotFoundException
    ):
        logger.warning(f"Contest team member not found: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="CONTEST_TEAM_MEMBER_NOT_FOUND",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(TeamDisqualifiedError)
    async def team_disqualified_handler(request: Request, exc: TeamDisqualifiedError):
        logger.warning(f"Team disqualified: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="TEAM_DISQUALIFIED",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(TeamIsConfirmedError)
    async def team_is_confirmed_handler(request: Request, exc: TeamIsConfirmedError):
        logger.warning(f"Team is confirmed: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="TEAM_IS_CONFIRMED",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(
        TeamStatusNotAllowedForUpdatingContestTeamMemberStatusException
    )
    async def team_status_not_allowed_for_updating_contest_team_member_status_handler(
        request: Request,
        exc: TeamStatusNotAllowedForUpdatingContestTeamMemberStatusException,
    ):
        logger.warning(
            f"Team status not allowed for updating contest team member status: {exc.message}"
        )
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="TEAM_STATUS_NOT_ALLOWED_FOR_UPDATING_CONTEST_TEAM_MEMBER_STATUS",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(InvalidContestTeamMemberStatusUpdateException)
    async def invalid_contest_team_member_status_update_handler(
        request: Request, exc: InvalidContestTeamMemberStatusUpdateException
    ):
        logger.warning(f"Invalid contest team member status update: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="INVALID_CONTEST_TEAM_MEMBER_STATUS_UPDATE",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(TeamAlreadyInContestError)
    async def team_already_in_contest_handler(
        request: Request, exc: TeamAlreadyInContestError
    ):
        logger.warning(f"Team already in contest: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="TEAM_ALREADY_IN_CONTEST",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(ContestMaxTeamsReachedError)
    async def contest_max_teams_reached_handler(
        request: Request, exc: ContestMaxTeamsReachedError
    ):
        logger.warning(f"Contest max teams reached: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="CONTEST_MAX_TEAMS_REACHED",
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

    @app.exception_handler(BankAccessDeniedError)
    async def bank_access_denied_handler(request: Request, exc: BankAccessDeniedError):
        logger.warning(f"Bank access denied: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="BANK_ACCESS_DENIED",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(BankAlreadyExistsError)
    async def bank_already_exists_handler(
        request: Request, exc: BankAlreadyExistsError
    ):
        logger.warning(f"Bank already exists: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="BANK_ALREADY_EXISTS",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(BankNotFoundError)
    async def bank_not_found_handler(request: Request, exc: BankNotFoundError):
        logger.warning(f"Bank not found: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="BANK_NOT_FOUND",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(BankOwnerUnshareError)
    async def bank_owner_unshare_error_handler(
        request: Request, exc: BankOwnerUnshareError
    ):
        logger.warning(f"Cannot unshare bank: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="BANK_OWNER_UNSHARE_ERROR",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(BankPermissionError)
    async def bank_permission_error_handler(request: Request, exc: BankPermissionError):
        logger.warning(f"Bank permission error: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="BANK_PERMISSION_ERROR",
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

    @app.exception_handler(InvalidContestStateError)
    async def invalid_contest_state_handler(
        request: Request, exc: InvalidContestStateError
    ):
        logger.warning(f"Invalid contest state: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="INVALID_CONTEST_STATE",
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

    @app.exception_handler(TeamNotHavingRequiredNumberOfMembersException)
    async def team_not_having_required_number_of_members_handler(
        request: Request, exc: TeamNotHavingRequiredNumberOfMembersException
    ):
        logger.warning(f"Team not having required number of members: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="TEAM_NOT_HAVING_REQUIRED_NUMBER_OF_MEMBERS",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(LeaderMustBeMemberError)
    async def leader_must_be_member_handler(
        request: Request, exc: LeaderMustBeMemberError
    ):
        logger.warning(f"Leader must be member: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="LEADER_MUST_BE_MEMBER",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(IndividualModeActionNotAllowedError)
    async def individual_mode_action_not_allowed_handler(
        request: Request, exc: IndividualModeActionNotAllowedError
    ):
        logger.warning(f"Individual mode action not allowed: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="INDIVIDUAL_MODE_ACTION_NOT_ALLOWED",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(StudentTeamInvitationNotFoundError)
    async def student_team_invitation_not_found_handler(
        request: Request, exc: StudentTeamInvitationNotFoundError
    ):
        logger.warning(f"Student team invitation not found: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="STUDENT_TEAM_INVITATION_NOT_FOUND",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(StudentTeamInvitationError)
    async def student_team_invitation_error_handler(
        request: Request, exc: StudentTeamInvitationError
    ):
        logger.warning(f"Student team invitation error: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="STUDENT_TEAM_INVITATION_ERROR",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(StudentTeamUserNotFoundError)
    async def student_team_user_not_found_handler(
        request: Request, exc: StudentTeamUserNotFoundError
    ):
        logger.warning(f"Student team user not found: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="STUDENT_TEAM_USER_NOT_FOUND",
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

    @app.exception_handler(ContestTeamProgressNotFoundError)
    async def contest_team_progress_not_found_error(
        request: Request, exc: ContestTeamProgressNotFoundError
    ):
        logger.warning(f"Contest Team Progress not found: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="CONTEST_TEAM_PROGRESS_NOT_FOUND",
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

    @app.exception_handler(InvalidImagePathError)
    async def invalid_image_path_handler(request: Request, exc: InvalidImagePathError):
        logger.warning(f"Invalid image path: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="INVALID_IMAGE_PATH",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(InvalidImageDataError)
    async def invalid_image_data_handler(request: Request, exc: InvalidImageDataError):
        logger.warning(f"Invalid image data: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="INVALID_IMAGE_DATA",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(ImageNotFoundError)
    async def image_not_found_handler(request: Request, exc: ImageNotFoundError):
        logger.warning(f"Image not found: {exc.detail}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="IMAGE_NOT_FOUND",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(ImageStorageError)
    async def image_storage_error_handler(request: Request, exc: ImageStorageError):
        logger.error(f"Image storage error: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="IMAGE_STORAGE_ERROR",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(TagNotFoundError)
    async def tag_not_found_handler(request: Request, exc: TagNotFoundError):
        logger.warning(f"Tag not found: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="TAG_NOT_FOUND",
            details=[exc.detail] if exc.detail else None,
        )

    @app.exception_handler(TagAlreadyExistsError)
    async def tag_already_exists_handler(request: Request, exc: TagAlreadyExistsError):
        logger.warning(f"Tag already exists: {exc.message}")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code="TAG_ALREADY_EXISTS",
            details=[exc.detail] if exc.detail else None,
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
