from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    can_create,
    can_delete,
    can_read,
    can_update,
    get_current_user_id,
)
from app.core.clients.database import get_db
from app.core.guards.contest import ContestOperationGuard
from app.core.logger import logger
from app.core.response import create_api_response
from app.repositories.contest import ContestRepository
from app.repositories.user import UserRepository
from app.schema.base import APIResponse
from app.schema.contest import (
    ContestCreate,
    ContestResponse,
    ContestSummaryResponse,
    ContestUpdate,
    InstructorManageRequest,
    InstructorResponse,
)
from app.service.contest_service import ContestService
from app.utils.enums import ContestStatus
from app.utils.pagination import get_pagination
from app.validators.contest import ContestValidator

router = APIRouter()


def get_contest_service(db: AsyncSession = Depends(get_db)) -> ContestService:
    """
    Dependency injector linking repository, guard, and validator into the service.

    Args:
        db (Session): Database session passed from FastAPI dependencies.

    Returns:
        ContestService: Fully configured service class instance.
    """
    contest_repository = ContestRepository(db)
    user_repository = UserRepository(db)
    guard = ContestOperationGuard(db)
    validator = ContestValidator()
    return ContestService(contest_repository, user_repository, guard, validator)


@router.post(
    "/",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new contest",
    dependencies=[can_create("contests")],
)
async def create_contest(
    request: Request,
    contest: ContestCreate,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestService = Depends(get_contest_service),
):
    """
    Create a new contest.

    Args:
        request (Request): Framework context.
        contest (ContestCreate): The contest data to create.
        user_id (UUID): The currently authenticated user ID via Keycloak.
        service (ContestService): Injected domain service handling contest operations.

    Returns:
        APIResponse: Standardized response encapsulating creation metadata.

    Raises:
        UnauthorizedError: If the caller is not authenticated.
        PermissionDeniedError: If the caller lacks create permission.
        RequestValidationError: If request payload validation fails.
        ContestAlreadyExistsError: If a contest with the same name already exists.
        InvalidContestError: If contest business validation fails.
        ContestOperationError: If contest creation fails unexpectedly.
    """
    created_contest = await service.create_contest(contest, user_id)
    logger.info(
        f"Contest '{created_contest.name}' with ID {created_contest.id} created (actor=REDACTED)"
    )

    return create_api_response(
        request,
        data=None,
        message="Contest created successfully",
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    "/",
    response_model=APIResponse[list[ContestSummaryResponse]],
    summary="Get all contests",
    dependencies=[can_read("contests")],
)
async def get_all_contests(
    request: Request,
    user_id: UUID = Depends(get_current_user_id),
    search: str | None = Query(None, description="Search by contest name"),
    contest_status: ContestStatus | None = Query(
        None, description="Filter by contest status"
    ),
    is_public: bool | None = Query(
        None, description="Filter by visibility (public/private)"
    ),
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of contests per page"),
    service: ContestService = Depends(get_contest_service),
):
    """
    Get all active contests accessible to the user.

    Args:
        request (Request): Framework context.
        user_id (UUID): Authenticated user ID.
        search (str | None): Optional string to search contest names.
        contest_status (ContestStatus | None): Optional filter for contest status.
        is_public (bool | None): Optional filter for visibility.
        page (int): Page number (starts from 1).
        page_size (int): Number of contests per page.
        service (ContestService): Injected domain service.

    Returns:
        APIResponse: Standardized response encapsulating the list of contests and pagination state.

    Raises:
        UnauthorizedError: If the caller is not authenticated.
        PermissionDeniedError: If the caller lacks read permission.
        RequestValidationError: If query parameter validation fails.
        ContestOperationError: If contest retrieval fails unexpectedly.
    """
    skip = (page - 1) * page_size
    total, contests = await service.get_all_contests(
        user_id, search, contest_status, is_public, skip, page_size
    )

    pagination = get_pagination(total=total, page=page, page_size=page_size)

    return create_api_response(
        request,
        data=contests,
        message="Contests fetched successfully",
        pagination=pagination,
    )


@router.get(
    "/deleted",
    response_model=APIResponse[list[ContestSummaryResponse]],
    summary="Get soft-deleted contests",
    dependencies=[can_read("contests")],
)
async def get_deleted_contests(
    request: Request,
    user_id: UUID = Depends(get_current_user_id),
    search: str | None = Query(None, description="Search by contest name"),
    contest_status: ContestStatus | None = Query(
        None, description="Filter by contest status"
    ),
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of contests per page"),
    service: ContestService = Depends(get_contest_service),
):
    """
    Get soft-deleted contests accessible to the user.

    Args:
        request (Request): Framework context.
        user_id (UUID): Authenticated user ID.
        search (str | None): Optional string to search contest names.
        contest_status (ContestStatus | None): Optional filter for contest status.
        page (int): Page number (starts from 1).
        page_size (int): Number of contests per page.
        service (ContestService): Injected domain service.

    Returns:
        APIResponse: Standardized response encapsulating the list of soft-deleted contests.

    Raises:
        UnauthorizedError: If the caller is not authenticated.
        PermissionDeniedError: If the caller lacks read permission.
        RequestValidationError: If query parameter validation fails.
        ContestOperationError: If contest retrieval fails unexpectedly.
    """
    skip = (page - 1) * page_size
    total, contests = await service.get_soft_deleted_contests(
        user_id, search, contest_status, skip, page_size
    )

    pagination = get_pagination(total=total, page=page, page_size=page_size)

    return create_api_response(
        request,
        data=contests,
        message="Deleted contests fetched successfully",
        pagination=pagination,
    )


@router.get(
    "/{contest_id}",
    response_model=APIResponse[ContestResponse],
    summary="Get contest by ID",
    dependencies=[can_read("contests")],
)
async def get_contest(
    request: Request,
    contest_id: UUID,
    service: ContestService = Depends(get_contest_service),
    user_id: UUID = Depends(get_current_user_id),
):
    """
    Get detailed information about a specific contest.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        service (ContestService): Injected domain service.
        user_id (UUID): Authenticated user ID.

    Returns:
        APIResponse: Detailed information block for the contest.

    Raises:
        UnauthorizedError: If the caller is not authenticated.
        PermissionDeniedError: If the caller lacks read permission.
        ContestNotFoundError: If the contest does not exist.
        ContestOperationError: If contest retrieval fails unexpectedly.
    """
    contest = await service.get_contest_by_id(contest_id, user_id)
    return create_api_response(
        request, data=contest, message="Contest fetched successfully"
    )


@router.patch(
    "/{contest_id}",
    response_model=APIResponse[ContestResponse],
    summary="Update contest",
    dependencies=[can_update("contests")],
)
async def update_contest(
    request: Request,
    contest_id: UUID,
    contest_data: ContestUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestService = Depends(get_contest_service),
):
    """
    Update contest details.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        contest_data (ContestUpdate): The fields to update.
        user_id (UUID): Authenticated user ID.
        service (ContestService): Injected domain service.

    Returns:
        APIResponse: Standardized response encapsulating the updated contest details.

    Raises:
        UnauthorizedError: If the caller is not authenticated.
        PermissionDeniedError: If the caller lacks update permission.
        RequestValidationError: If request payload validation fails.
        ContestNotFoundError: If the contest does not exist.
        InvalidContestError: If contest business validation fails.
        ContestOperationError: If contest update fails unexpectedly.
    """
    contest = await service.update_contest(contest_id, contest_data, user_id)
    logger.info(f"Contest with ID {contest_id} updated (actor=REDACTED)")

    return create_api_response(
        request,
        data=contest,
        message="Contest updated successfully",
    )


@router.post(
    "/{contest_id}/publish",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    summary="Publish contest",
    dependencies=[can_update("contests")],
)
async def publish_contest(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestService = Depends(get_contest_service),
):
    """
    Publish a contest.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest to publish.
        user_id (UUID): Authenticated user ID.
        service (ContestService): Injected domain service.

    Returns:
        APIResponse: Success confirmation.

    Raises:
        UnauthorizedError: If the caller is not authenticated.
        PermissionDeniedError: If the caller lacks update permission.
        ContestNotFoundError: If the contest does not exist.
        InvalidContestError: If contest cannot be published in its current state.
        ContestOperationError: If contest publish fails unexpectedly.
    """
    await service.publish_contest(contest_id, user_id)
    logger.info(f"Contest with ID {contest_id} published (actor=REDACTED)")

    return create_api_response(
        request,
        data=None,
        message="Contest published successfully",
    )


@router.delete(
    "/{contest_id}",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete contest",
    dependencies=[can_delete("contests")],
)
async def delete_contest(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestService = Depends(get_contest_service),
):
    """
    Hard delete a contest.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest to delete.
        user_id (UUID): Authenticated user ID.
        service (ContestService): Injected domain service.

    Returns:
        APIResponse: Success confirmation.

    Raises:
        UnauthorizedError: If the caller is not authenticated.
        PermissionDeniedError: If the caller lacks delete permission.
        ContestNotFoundError: If the contest does not exist.
        ContestOperationError: If contest deletion fails unexpectedly.
    """
    await service.delete_contest(contest_id, user_id)
    logger.info(f"Contest with ID {contest_id} deleted (actor=REDACTED)")

    return create_api_response(
        request,
        data=None,
        message="Contest deleted successfully",
    )


@router.delete(
    "/{contest_id}/soft-delete",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    summary="Soft delete contest",
    dependencies=[can_delete("contests")],
)
async def soft_delete_contest(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestService = Depends(get_contest_service),
):
    """
    Soft delete a contest without physically removing it.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest to soft delete.
        user_id (UUID): Authenticated user ID.
        service (ContestService): Injected domain service.

    Returns:
        APIResponse: Success confirmation.

    Raises:
        UnauthorizedError: If the caller is not authenticated.
        PermissionDeniedError: If the caller lacks delete permission.
        ContestNotFoundError: If the contest does not exist.
        ContestOperationError: If contest soft deletion fails unexpectedly.
    """
    await service.soft_delete_contest(contest_id, user_id)
    logger.info(f"Contest {contest_id} soft deleted (actor=REDACTED)")

    return create_api_response(
        request,
        data=None,
        message="Contest soft deleted successfully",
    )


@router.post(
    "/{contest_id}/restore",
    response_model=APIResponse[ContestResponse],
    status_code=status.HTTP_200_OK,
    summary="Restore soft-deleted contest",
    dependencies=[can_update("contests")],
)
async def restore_contest(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestService = Depends(get_contest_service),
):
    """
    Restore a soft-deleted contest.

    Returns the contest to an active status.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest to restore.
        user_id (UUID): Authenticated user ID.
        service (ContestService): Injected domain service.

    Returns:
        APIResponse: Standardized response encapsulating the restored contest data.

    Raises:
        UnauthorizedError: If the caller is not authenticated.
        PermissionDeniedError: If the caller lacks update permission.
        ContestNotFoundError: If the contest does not exist.
        InvalidContestError: If contest cannot be restored in its current state.
        ContestOperationError: If contest restoration fails unexpectedly.
    """
    contest = await service.restore_contest(contest_id, user_id)
    logger.info(f"Contest {contest_id} restored (actor=REDACTED)")
    return create_api_response(
        request, data=contest, message="Contest restored successfully"
    )


@router.post(
    "/{contest_id}/instructors",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign instructors to contest",
    dependencies=[can_update("contests")],
)
async def assign_instructors_to_contest(
    request: Request,
    contest_id: UUID,
    instructor_request: InstructorManageRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestService = Depends(get_contest_service),
):
    """
    Assign instructors to a contest.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        instructor_request (InstructorManageRequest): Request containing instructor IDs.
        user_id (UUID): Authenticated user ID.
        service (ContestService): Injected domain service.

    Returns:
        APIResponse: Success confirmation.

    Raises:
        UnauthorizedError: If the caller is not authenticated.
        PermissionDeniedError: If the caller lacks update permission.
        RequestValidationError: If request payload validation fails.
        ContestNotFoundError: If the contest does not exist.
        InstructorNotFoundError: If an instructor ID is invalid.
        InstructorAlreadyAssignedError: If an instructor is already assigned.
        ContestOperationError: If instructor assignment fails unexpectedly.
    """
    await service.assign_instructors_to_contest(contest_id, instructor_request, user_id)
    logger.info(
        f"Assigned {len(instructor_request.instructor_ids)} instructors to contest {contest_id} (actor=REDACTED)"
    )

    return create_api_response(
        request,
        data=None,
        message="Instructors assigned successfully",
    )


@router.delete(
    "/{contest_id}/instructors",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove instructors from contest",
    dependencies=[can_update("contests")],
)
async def remove_instructors_from_contest(
    request: Request,
    contest_id: UUID,
    instructor_request: InstructorManageRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestService = Depends(get_contest_service),
):
    """
    Remove instructors from a contest.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        instructor_request (InstructorManageRequest): Request containing instructor IDs to remove.
        user_id (UUID): Authenticated user ID.
        service (ContestService): Injected domain service.

    Returns:
        APIResponse: Success confirmation.

    Raises:
        UnauthorizedError: If the caller is not authenticated.
        PermissionDeniedError: If the caller lacks update permission.
        RequestValidationError: If request payload validation fails.
        ContestNotFoundError: If the contest does not exist.
        InstructorNotAssignedError: If an instructor is not currently assigned.
        ContestOperationError: If instructor removal fails unexpectedly.
    """
    await service.remove_instructors_from_contest(
        contest_id, instructor_request, user_id
    )
    logger.info(
        f"Removed {len(instructor_request.instructor_ids)} instructors from contest {contest_id} (actor=REDACTED)"
    )

    return create_api_response(
        request,
        data=None,
        message="Instructors removed successfully",
    )


@router.get(
    "/{contest_id}/instructors",
    response_model=APIResponse[list[InstructorResponse]],
    summary="Get contest instructors",
    dependencies=[can_read("contests")],
)
async def get_contest_instructors(
    request: Request,
    contest_id: UUID,
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(
        10, ge=1, le=100, description="Number of instructors per page"
    ),
    service: ContestService = Depends(get_contest_service),
    user_id: UUID = Depends(get_current_user_id),
):
    """
    Get paginated list of instructors for a contest.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        page (int): Page number (starts from 1).
        page_size (int): Number of instructors per page.
        service (ContestService): Injected domain service.
        user_id (UUID): Authenticated user ID.

    Returns:
        APIResponse: Standardized response with list of instructors and pagination state.

    Raises:
        UnauthorizedError: If the caller is not authenticated.
        PermissionDeniedError: If the caller lacks read permission.
        RequestValidationError: If query parameter validation fails.
        ContestNotFoundError: If the contest does not exist.
        ContestOperationError: If instructor retrieval fails unexpectedly.
    """
    skip = (page - 1) * page_size
    total, instructors = await service.get_contest_instructors(
        contest_id, user_id, skip, page_size
    )
    logger.info(f"Retrieved {len(instructors)} instructors for contest {contest_id}")

    pagination = get_pagination(total=total, page=page, page_size=page_size)

    return create_api_response(
        request,
        data=instructors,
        message="Instructors fetched successfully",
        pagination=pagination,
    )
