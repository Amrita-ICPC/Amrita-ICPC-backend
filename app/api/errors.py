from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, NoResultFound, SQLAlchemyError

from app.core.logger import logger
from app.exceptions.base import AppBaseException
from app.exceptions.contest import (
    ContestAlreadyExistsError,
    ContestNotFoundError,
    ContestOperationError,
    InstructorAlreadyAssignedError,
    InstructorNotAssignedError,
    InstructorNotFoundError,
    InvalidContestError,
)
from app.exceptions.team import (
    TeamNotFoundError,
)


def setup_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers for the FastAPI application."""

    @app.exception_handler(AppBaseException)
    async def app_exception_handler(request: Request, exc: AppBaseException):
        logger.warning(f"App exception: {exc.message} (Status: {exc.status_code})")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "message": exc.message},
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

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": sanitized_errors, "message": "Validation error"},
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
        logger.error(f"Database error: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error",
                "message": "A database error occurred",
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_exception_handler(request: Request, exc: IntegrityError):
        logger.error(f"Integrity error: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Conflict",
                "message": "Data integrity violation (e.g., duplicate entry)",
            },
        )

    @app.exception_handler(NoResultFound)
    async def no_result_exception_handler(request: Request, exc: NoResultFound):
        logger.warning(f"No result found: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Not Found", "message": "Requested resource not found"},
        )

    @app.exception_handler(ContestNotFoundError)
    async def contest_not_found_handler(request: Request, exc: ContestNotFoundError):
        logger.warning(f"Contest not found: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "message": exc.message},
        )

    @app.exception_handler(ContestAlreadyExistsError)
    async def contest_already_exists_handler(
        request: Request, exc: ContestAlreadyExistsError
    ):
        logger.warning(f"Contest already exists: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "message": exc.message},
        )

    @app.exception_handler(InvalidContestError)
    async def invalid_contest_handler(request: Request, exc: InvalidContestError):
        logger.warning(f"Invalid contest data: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "message": exc.message},
        )

    @app.exception_handler(ContestOperationError)
    async def contest_operation_error_handler(
        request: Request, exc: ContestOperationError
    ):
        logger.error(f"Contest operation error: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "message": exc.message},
        )

    @app.exception_handler(InstructorAlreadyAssignedError)
    async def instructor_already_assigned_handler(
        request: Request, exc: InstructorAlreadyAssignedError
    ):
        logger.warning(f"Instructor already assigned: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "message": exc.message},
        )

    @app.exception_handler(InstructorNotAssignedError)
    async def instructor_not_assigned_handler(
        request: Request, exc: InstructorNotAssignedError
    ):
        logger.warning(f"Instructor not assigned: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "message": exc.message},
        )

    @app.exception_handler(InstructorNotFoundError)
    async def instructor_not_found_handler(
        request: Request, exc: InstructorNotFoundError
    ):
        logger.warning(f"Instructor not found: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "message": exc.message},
        )

    @app.exception_handler(TeamNotFoundError)
    async def team_not_found_handler(request: Request, exc: TeamNotFoundError):
        logger.warning(f"Team not found: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "message": exc.message},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error",
                "message": "An unexpected error occurred",
            },
        )
