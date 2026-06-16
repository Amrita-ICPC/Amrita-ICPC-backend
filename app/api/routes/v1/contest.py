from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    can_create,
    can_delete,
    can_read,
    can_update,
    check_permission,
    get_current_user_id,
)
from app.core.clients.database import get_db
from app.core.clients.redis import get_redis
from app.core.guards.contest import ContestOperationGuard
from app.core.logger import logger
from app.core.response import create_api_response
from app.repositories.audience import AudienceRepository
from app.repositories.bank import BankRepository
from app.repositories.contest import ContestRepository
from app.repositories.evaluation import EvaluationRepository
from app.repositories.language import LanguageRepository
from app.repositories.question import QuestionRepository
from app.repositories.submission import ContestSubmissionRepository
from app.repositories.team import TeamRepository
from app.repositories.user import UserRepository
from app.schema.base import APIResponse
from app.schema.contest import (
    AddContestQuestionsRequest,
    ContestAudienceManageRequest,
    ContestAudienceResponse,
    ContestBankCloneRequest,
    ContestCreate,
    ContestQuestionResponse,
    ContestResponse,
    ContestSummaryResponse,
    ContestUpdate,
    InstructorManageRequest,
    InstructorResponse,
    MessageResponse,
    RemoveContestQuestionRequest,
    ReorderContestQuestionsRequest,
)
from app.schema.evaluation import EvaluationResponse, EvaluationStatusResponse
from app.schema.question import (
    ContestQuestionsListResponse,
    QuestionResponse,
    QuestionUpdate,
)
from app.schema.submission import ContestDashboardResponse
from app.service.contest_dashboard_service import ContestDashboardService
from app.service.contest_event_publish import ContestEventPublisher
from app.service.contest_question_service import ContestQuestionService
from app.service.contest_service import ContestService
from app.utils.enums import (
    ContestRunStatus,
    ContestStatus,
    QuestionDifficulty,
    SortOrder,
)
from app.utils.pagination import get_pagination
from app.validators.contest import ContestValidator

router = APIRouter()


def get_contest_service(
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
) -> ContestService:
    """
    Dependency injector linking repository, guard, and validator into the service.

    Args:
        db (AsyncSession): Database session passed from FastAPI dependencies.
        redis_client (Redis): Redis client instance.

    Returns:
        ContestService: Fully configured service class instance.
    """
    contest_repository = ContestRepository(db)
    user_repository = UserRepository(db)
    QuestionRepository(db)
    audience_repository = AudienceRepository(db)
    LanguageRepository(db)
    team_repository = TeamRepository(db)
    guard = ContestOperationGuard(db)
    validator = ContestValidator()
    event_publisher = ContestEventPublisher(redis_client)
    evaluation_repository = EvaluationRepository(db)
    return ContestService(
        repository=contest_repository,
        user_repository=user_repository,
        guard=guard,
        validator=validator,
        audience_repository=audience_repository,
        team_repository=team_repository,
        event_publisher=event_publisher,
        evaluation_repository=evaluation_repository,
        redis=redis_client,
    )


def get_contest_question_service(
    db: AsyncSession = Depends(get_db),
) -> ContestQuestionService:
    """Dependency injector for ContestQuestionService."""
    contest_repository = ContestRepository(db)
    question_repository = QuestionRepository(db)
    language_repository = LanguageRepository(db)
    bank_repository = BankRepository(db)
    guard = ContestOperationGuard(db)
    validator = ContestValidator()
    return ContestQuestionService(
        contest_repository,
        guard,
        validator,
        question_repository,
        language_repository,
        bank_repository,
    )


def get_contest_dashboard_service(
    db: AsyncSession = Depends(get_db),
) -> ContestDashboardService:
    """Dependency injector for ContestDashboardService."""
    contest_repository = ContestRepository(db)
    submission_repository = ContestSubmissionRepository(db)
    guard = ContestOperationGuard(db)
    return ContestDashboardService(
        contest_repository=contest_repository,
        submission_repository=submission_repository,
        guard=guard,
    )


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
        None, description="Filter by contest lifecycle status (DRAFT/PUBLISHED/etc)"
    ),
    run_status: ContestRunStatus | None = Query(
        None, description="Filter by contest run-state (UPCOMING/LIVE/ENDED)"
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
        contest_status (ContestStatus | None): Optional filter for lifecycle status.
        run_status (ContestRunStatus | None): Optional filter for temporal run-state.
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
        user_id, search, contest_status, run_status, is_public, skip, page_size
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


@router.get(
    "/{contest_id}/dashboard",
    response_model=APIResponse[ContestDashboardResponse],
    summary="Get contest submission dashboard analytics",
    dependencies=[can_read("contests")],
)
async def get_contest_dashboard(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestDashboardService = Depends(get_contest_dashboard_service),
):
    """
    Get the contest submission dashboard and aggregate analytics.

    Only accessible by the contest creator, assigned instructors, or administrators.
    """
    result = await service.get_dashboard_analytics(
        contest_id=contest_id, user_id=user_id
    )
    logger.info(f"Successfully retrieved dashboard analytics for contest: {contest_id}")
    return create_api_response(
        request,
        data=result,
        message="Contest dashboard analytics retrieved successfully",
    )


@router.get(
    "/{contest_id}/questions",
    response_model=APIResponse[ContestQuestionsListResponse],
    summary="Get contest questions",
    dependencies=[can_read("contests"), can_read("contests:questions")],
)
async def get_contest_questions(
    request: Request,
    contest_id: UUID,
    search: str | None = Query(None, description="Search by question text"),
    difficulty: QuestionDifficulty | None = Query(
        None, description="Filter by question difficulty"
    ),
    language_id: int | None = Query(
        None, gt=0, description="Filter by allowed language ID"
    ),
    tag_id: UUID | None = Query(None, description="Filter by tag ID"),
    tag_name: str | None = Query(None, description="Filter by tag name"),
    sort_by: str | None = Query(None, description="Sort by field (e.g., 'difficulty')"),
    sort_order: str = Query("asc", regex="^(asc|desc)$", description="Sort order"),
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(
        10, ge=1, le=100, description="Number of questions per page"
    ),
    service: ContestQuestionService = Depends(get_contest_question_service),
    user_id: UUID = Depends(get_current_user_id),
) -> APIResponse[ContestQuestionsListResponse]:
    """
    Get paginated contest questions.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        search (str): Optional search term for question title.
        difficulty (str): Optional difficulty filter.
        language_id (int): Optional language filter.
        tag_id (UUID): Optional tag filter.
        page (int): Page number (starts from 1).
        page_size (int): Number of questions per page.
        service (ContestQuestionService): Injected domain service.
        user_id (UUID): Authenticated user ID.

    Returns:
        APIResponse: Standardized response with list of questions and pagination state.
    """
    skip = (page - 1) * page_size
    # Convert sort_order string to SortOrder enum
    sort_order_enum = SortOrder(sort_order) if sort_order else SortOrder.ASC
    result = await service.get_contest_questions(
        contest_id=contest_id,
        user_id=user_id,
        search_term=search,
        difficulty=difficulty,
        language_id=language_id,
        tag_id=tag_id,
        tag_name=tag_name,
        sort_by=sort_by,
        sort_order=sort_order_enum,
        skip=skip,
        limit=page_size,
    )

    pagination = get_pagination(
        total=result.total_count, page=page, page_size=page_size
    )
    return create_api_response(
        request,
        data=result,
        message="Contest questions fetched successfully",
        pagination=pagination,
    )


@router.get(
    "/{contest_id}/questions/{question_id}",
    response_model=APIResponse[QuestionResponse],
    summary="Get contest question by ID",
    dependencies=[can_read("contests"), can_read("contests:questions")],
)
async def get_contest_question(
    request: Request,
    contest_id: UUID,
    question_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestQuestionService = Depends(get_contest_question_service),
) -> APIResponse[QuestionResponse]:
    """
    Get a contest question by ID.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        question_id (UUID): The unique identifier of the question.
        user_id (UUID): Authenticated user ID.
        service (ContestQuestionService): Injected domain service.

    Returns:
        APIResponse: The question details.
    """
    question = await service.get_contest_question(contest_id, question_id, user_id)
    logger.info(
        f"Fetched question {question_id} from contest {contest_id} (actor=REDACTED)"
    )
    return create_api_response(
        request,
        data=question,
        message="Contest question fetched successfully",
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
    dependencies=[
        can_update("contests"),
        Depends(check_permission("contests", "publish")),
    ],
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
    dependencies=[
        can_update("contests"),
        Depends(check_permission("contests", "manamge_instructors")),
    ],
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
    dependencies=[
        can_update("contests"),
        Depends(check_permission("contests", "manage_instructors")),
    ],
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
    dependencies=[can_read("contests"), can_read("contests:instructors")],
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


@router.post(
    "/{contest_id}/questions",
    response_model=APIResponse[list[ContestQuestionResponse]],
    status_code=status.HTTP_201_CREATED,
    summary="Add questions to contest",
    dependencies=[can_update("contests"), can_create("contests:questions")],
)
async def add_question_to_contest(
    request: Request,
    contest_id: UUID,
    questions_request: AddContestQuestionsRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestQuestionService = Depends(get_contest_question_service),
) -> APIResponse[list[ContestQuestionResponse]]:
    """
    Add multiple questions to a contest in batch.

    Adds one or more questions to a specific contest and assigns metadata for each,
    including position, time duration, and point value. Only contest creators
    and assigned instructors can perform this operation.

    Args:
        request (Request): HTTP request context.
        contest_id (UUID): The contest to add questions to.
        questions_request (AddContestQuestionsRequest): Contains list of questions with
                                                         question_id, order, duration, score.
        user_id (UUID): Authenticated user ID.
        service (ContestService): Contest service dependency.

    Returns:
        APIResponse[list[ContestQuestionResponse]]: List of created contest-question relationships.

    Raises:
        HTTPException (400): If question metadata is invalid (order/duration/score <= 0).
        HTTPException (401): If user is not authenticated.
        HTTPException (403): If user lacks contest management permission.
        HTTPException (404): If contest or questions do not exist.
        HTTPException (409): If any question is already in the contest.
    """
    contest_questions = await service.add_questions_to_contest(
        contest_id, questions_request, user_id
    )
    logger.info(
        f"Added {len(questions_request.questions)} questions to contest {contest_id} (actor=REDACTED)"
    )

    return create_api_response(
        request,
        data=contest_questions,
        message="Questions added to contest successfully",
        status_code=status.HTTP_201_CREATED,
    )


@router.delete(
    "/{contest_id}/questions",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Remove questions from contest",
    dependencies=[can_update("contests"), can_delete("contests:questions")],
)
async def remove_question_from_contest(
    request: Request,
    contest_id: UUID,
    questions_request: RemoveContestQuestionRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestQuestionService = Depends(get_contest_question_service),
) -> APIResponse[None]:
    """
    Remove multiple questions from a contest in batch.

    Removes one or more questions from a specific contest. Only contest creators
    and assigned instructors can perform this operation.

    Args:
        request (Request): HTTP request context.
        contest_id (UUID): The contest to remove questions from.
        questions_request (RemoveContestQuestionRequest): Contains list of question IDs.
        user_id (UUID): Authenticated user ID.
        service (ContestService): Contest service dependency.

    Returns:
        APIResponse: Confirmation of successful removal.

    Raises:
        HTTPException (401): If user is not authenticated.
        HTTPException (403): If user lacks contest management permission.
        HTTPException (404): If contest does not exist or any question is not in contest.
    """
    await service.remove_questions_from_contest(contest_id, questions_request, user_id)
    logger.info(
        f"Removed {len(questions_request.question_ids)} questions from contest {contest_id} (actor=REDACTED)"
    )

    return create_api_response(
        request,
        data=None,
        message="Questions removed from contest successfully",
    )


@router.patch(
    "/{contest_id}/questions/reorder",
    response_model=APIResponse[MessageResponse],
    summary="Reorder contest questions",
    dependencies=[can_update("contests:questions")],
)
async def reorder_contest_questions(
    request: Request,
    contest_id: UUID,
    reorder_request: ReorderContestQuestionsRequest,
    service: ContestQuestionService = Depends(get_contest_question_service),
    user_id: UUID = Depends(get_current_user_id),
) -> APIResponse[MessageResponse]:
    """
    Update the ordering of questions within a contest.

    Args:
        contest_id: UUID of the target contest.
        reorder_request: List of question IDs and their new sequential orders.

    Returns:
        MessageResponse: Confirmation of reorder success.

    Raises:
        ContestNotFoundError: If the contest is not found.
        PermissionDeniedError: If the user lacks management rights.
        InvalidContestError: If the new ordering is non-sequential or contains duplicates.
    """
    await service.reorder_contest_questions(contest_id, reorder_request, user_id)
    return create_api_response(
        request,
        data=MessageResponse(message="Contest questions reordered successfully"),
        message="Contest questions reordered successfully",
    )


@router.post(
    "/{contest_id}/questions/clone-from-bank",
    response_model=APIResponse[list[ContestQuestionResponse]],
    status_code=status.HTTP_201_CREATED,
    summary="Clone questions from a bank into a contest",
    dependencies=[can_create("contests:questions")],
)
async def clone_questions_from_bank(
    request: Request,
    contest_id: UUID,
    clone_request: ContestBankCloneRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestQuestionService = Depends(get_contest_question_service),
) -> APIResponse[list[ContestQuestionResponse]]:
    """
    Clone questions from a bank into a contest.

    Args:
        request: Framework context.
        contest_id: UUID of the target contest.
        clone_request: DTO containing bank ID and selection criteria.
        user_id: Authenticated user ID.
        service: Injected domain service.

    Returns:
        APIResponse: Standardized response with list of created contest-question relationships.
    """
    results = await service.clone_questions_from_bank(
        contest_id, clone_request, user_id
    )
    logger.info(
        f"Cloned {len(results)} questions from bank {clone_request.bank_id} to contest {contest_id} (actor=REDACTED)"
    )
    return create_api_response(
        request,
        data=results,
        message=f"Successfully cloned {len(results)} questions from bank into contest",
        status_code=status.HTTP_201_CREATED,
    )


@router.post(
    "/{contest_id}/audiences",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign audiences to contest",
    dependencies=[can_update("contests")],
)
async def assign_audiences_to_contest(
    request: Request,
    contest_id: UUID,
    audience_request: ContestAudienceManageRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestService = Depends(get_contest_service),
):
    """
    Assign audiences to a contest.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        audience_request (ContestAudienceManageRequest): Request containing audience IDs.
        user_id (UUID): Authenticated user ID.
        service (ContestService): Injected domain service.

    Returns:
        APIResponse: Success confirmation.
    """
    await service.assign_audiences_to_contest(
        contest_id, audience_request.audience_ids, user_id
    )
    logger.info(
        f"Assigned {len(audience_request.audience_ids)} audiences to contest {contest_id} (actor=REDACTED)"
    )

    return create_api_response(
        request,
        data=None,
        message="Audiences assigned successfully",
    )


@router.delete(
    "/{contest_id}/audiences",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove audiences from contest",
    dependencies=[can_update("contests")],
)
async def remove_audiences_from_contest(
    request: Request,
    contest_id: UUID,
    audience_request: ContestAudienceManageRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestService = Depends(get_contest_service),
):
    """
    Remove audiences from a contest.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        audience_request (ContestAudienceManageRequest): Request containing audience IDs to remove.
        user_id (UUID): Authenticated user ID.
        service (ContestService): Injected domain service.

    Returns:
        APIResponse: Success confirmation.
    """
    await service.remove_audiences_from_contest(
        contest_id, audience_request.audience_ids, user_id
    )
    logger.info(
        f"Removed {len(audience_request.audience_ids)} audiences from contest {contest_id} (actor=REDACTED)"
    )

    return create_api_response(
        request,
        data=None,
        message="Audiences removed successfully",
    )


@router.get(
    "/{contest_id}/audiences",
    response_model=APIResponse[list[ContestAudienceResponse]],
    summary="Get contest audiences",
    dependencies=[can_read("contests")],
)
async def get_contest_audiences(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestService = Depends(get_contest_service),
):
    """
    Get audiences for a contest.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        user_id (UUID): Authenticated user ID.
        service (ContestService): Injected domain service.

    Returns:
        APIResponse: List of audiences for the contest.
    """
    audiences = await service.get_contest_audiences(contest_id, user_id)
    logger.info(f"Retrieved {len(audiences)} audiences for contest {contest_id}")

    return create_api_response(
        request,
        data=audiences,
        message="Audiences fetched successfully",
    )


@router.patch(
    "/{contest_id}/questions/{question_id}",
    response_model=APIResponse[QuestionResponse],
    status_code=status.HTTP_200_OK,
    summary="Comprehensive update of a contest question",
    dependencies=[can_update("contests:questions")],
)
async def update_contest_question(
    request: Request,
    contest_id: UUID,
    question_id: UUID,
    payload: QuestionUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestQuestionService = Depends(get_contest_question_service),
) -> APIResponse[QuestionResponse]:
    """
    Perform a comprehensive update of a contest question.

    Updates metadata, tags, templates, and test cases in a single operation.
    Only contest creators and assigned instructors can perform this operation.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        question_id (UUID): The unique identifier of the question.
        payload (QuestionUpdate): The update data.
        user_id (UUID): Authenticated user ID.
        service (ContestService): Injected domain service.

    Returns:
        APIResponse[QuestionResponse]: The updated question.
    """
    question = await service.update_contest_question(
        contest_id, question_id, payload, user_id
    )
    logger.info(
        f"Bulk updated question {question_id} in contest {contest_id} (actor=REDACTED)"
    )
    return create_api_response(
        request,
        data=question,
        message="Contest question updated successfully",
    )


@router.post(
    "/{contest_id}/cancel",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel a contest",
    dependencies=[Depends(check_permission("contests", "cancel"))],
)
async def cancel_contest(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestService = Depends(get_contest_service),
):
    """
    Cancel a contest.
    """
    await service.cancel_contest(contest_id, user_id)
    logger.info(f"Contest {contest_id} cancelled (actor=REDACTED)")
    return create_api_response(
        request,
        data=None,
        message="Contest cancelled successfully",
    )


@router.post(
    "/{contest_id}/evaluation",
    response_model=APIResponse[EvaluationResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger contest evaluation",
    dependencies=[can_update("contests")],
)
async def evaluate_contest(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestService = Depends(get_contest_service),
) -> APIResponse[EvaluationResponse]:
    """Trigger re-evaluation of all submissions in a contest.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        user_id (UUID): Authenticated user ID.
        service (ContestService): Injected domain service.

    Returns:
        APIResponse[EvaluationResponse]: The created evaluation process state.
    """
    evaluation = await service.evaluate_contest(contest_id, user_id)
    logger.info(f"Contest evaluation triggered for {contest_id} by user {user_id}")
    return create_api_response(
        request,
        data=evaluation,
        message="Contest evaluation triggered successfully",
        status_code=status.HTTP_202_ACCEPTED,
    )


@router.get(
    "/{contest_id}/evaluation/{evaluation_id}",
    response_model=APIResponse[EvaluationStatusResponse],
    status_code=status.HTTP_200_OK,
    summary="Get contest evaluation status",
    dependencies=[can_update("contests")],
)
async def get_evaluation_status(
    request: Request,
    contest_id: UUID,
    evaluation_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestService = Depends(get_contest_service),
) -> APIResponse[EvaluationStatusResponse]:
    """Get the status of a contest evaluation process.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        evaluation_id (UUID): The unique identifier of the evaluation record.
        user_id (UUID): Authenticated user ID.
        service (ContestService): Injected domain service.

    Returns:
        APIResponse[EvaluationStatusResponse]: Current evaluation status and metrics.
    """
    evaluation_status = await service.get_evaluation_status(
        contest_id, evaluation_id, user_id
    )
    logger.info(
        f"Contest evaluation status retrieved for {contest_id}, eval_id {evaluation_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=evaluation_status,
        message="Contest evaluation status retrieved successfully",
        status_code=status.HTTP_200_OK,
    )
