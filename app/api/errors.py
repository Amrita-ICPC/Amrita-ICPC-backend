from datetime import datetime, timezone

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, NoResultFound, SQLAlchemyError

from app.core.logger import logger
from app.exceptions.base import AppBaseException
from app.exceptions.execution import CompilationError
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
    """Register exception handlers for the FastAPI application.

    Every domain exception in app/exceptions/** derives from AppBaseException
    and already carries its own status_code plus an optional class-level
    error_code (see AppBaseException). That means one handler below --
    app_exception_handler -- covers all of them; a dedicated per-exception
    handler is only needed when a response must take a genuinely different
    shape (CompilationError) or the exception isn't an AppBaseException at
    all (RequestValidationError, SQLAlchemyError/IntegrityError/NoResultFound,
    and the final catch-all).
    """

    @app.exception_handler(AppBaseException)
    async def app_exception_handler(request: Request, exc: AppBaseException):
        log = logger.error if exc.status_code >= 500 else logger.warning
        log(f"{exc.__class__.__name__}: {exc.message} (status={exc.status_code})")
        return _create_error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.message,
            error_code=exc.error_code or exc.__class__.__name__,
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
