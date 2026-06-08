# TODO: Implement RBAC auth gaurd
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user_id
from app.core.clients.database import get_db
from app.core.clients.redis import get_redis
from app.core.guards.contest_student import ContestStudentGuard
from app.core.guards.team_student import TeamStudentGuard
from app.core.logger import logger
from app.core.response import create_api_response
from app.repositories.contest import ContestRepository
from app.repositories.contest_team_progress import ContestTeamProgressRepository
from app.repositories.dto.pagination import PaginationParams
from app.repositories.student.contest import StudentContestRepository
from app.repositories.student.contest_team import ContestTeamRepository
from app.repositories.student.team import StudentTeamRepository
from app.repositories.team import TeamRepository
from app.schema.base import APIResponse
from app.schema.student.contest_team import (
    ContestTeamInviteRequest,
    ContestTeamLeaderTransfer,
    ContestTeamMemberStatusUpdate,
    ContestTeamStatusUpdate,
    ContestTeamUpdate,
)
from app.schema.student.contest_team_progress import ContestTeamProgressResponse
from app.schema.student.contests import (
    StudentContestDetailsResponse,
    StudentContestListResponse,
    StudentContestRegistrationRequest,
    StudentContestStatusResponse,
)
from app.schema.team import ContestTeamCreate, ContestTeamImport
from app.service.student.contest_team import ContestTeamService
from app.service.student.contests import StudentContestService

router = APIRouter()


def get_student_contest_service(
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
) -> StudentContestService:
    repository = StudentContestRepository(db)
    contest_repository = ContestRepository(db)
    team_repository = TeamRepository(db)
    contest_student_guard = ContestStudentGuard(db)
    contest_team_repository = ContestTeamRepository(db)
    contest_team_progress_repository = ContestTeamProgressRepository(db)
    return StudentContestService(
        repository=repository,
        contest_repository=contest_repository,
        contest_team_reposiotry=contest_team_repository,
        team_repository=team_repository,
        contest_student_guard=contest_student_guard,
        contest_team_progress_repository=contest_team_progress_repository,
        redis=redis_client,
    )


def get_contest_team_service(
    db: AsyncSession = Depends(get_db),
) -> ContestTeamService:
    repository = ContestTeamRepository(db)
    team_repository = StudentTeamRepository(db)
    team_student_guard = TeamStudentGuard(db)
    contest_repository = ContestRepository(db)
    contest_student_guard = ContestStudentGuard(db)
    return ContestTeamService(
        repository=repository,
        team_repository=team_repository,
        team_student_guard=team_student_guard,
        contest_repository=contest_repository,
        contest_student_guard=contest_student_guard,
    )


@router.get(
    "/",
    response_model=APIResponse[StudentContestListResponse],
    summary="Get available contests for student",
)
async def get_student_contests(
    request: Request,
    filters: StudentContestRegistrationRequest = Depends(),
    search: str | None = Query(None, description="Search by contest name"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestService = Depends(get_student_contest_service),
):
    """
    Get all published contests available to the student.
    Filter by registration status and contest run status.
    """
    pagination_params = PaginationParams(
        skip=(page - 1) * page_size,
        limit=page_size,
    )

    result = await service.get_all_contests(
        user_id=user_id,
        request=filters,
        search=search,
        pagination=pagination_params,
    )

    return create_api_response(
        request,
        data=result,
        message="Student contests fetched successfully",
    )


@router.get(
    "/{contest_id}",
    response_model=APIResponse[StudentContestDetailsResponse],
    summary="Get contest details for student",
)
async def get_student_contest_by_id(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestService = Depends(get_student_contest_service),
):
    """
    Get contest details for student.
    """
    result = await service.get_contest_by_id(contest_id, user_id)
    return create_api_response(
        request,
        data=result,
        message="Student contest details fetched successfully",
    )


@router.get(
    "/{contest_id}/participation/me",
    response_model=APIResponse[StudentContestStatusResponse],
    summary="Get student participation status in a contest",
)
async def get_student_contest_status(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestService = Depends(get_student_contest_service),
):
    """
    Get student participation status in a contest, including team details and readiness.
    """
    result = await service.get_student_participation_status_in_contest(
        contest_id, user_id
    )
    return create_api_response(
        request,
        data=result,
        message="Student contest status fetched successfully",
    )


@router.post(
    "/{contest_id}/teams/import",
    response_model=APIResponse[None],
    summary="Import an existing student team into a contest",
)
async def import_student_team(
    request: Request,
    contest_id: UUID,
    contest_team_import: ContestTeamImport,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestTeamService = Depends(get_contest_team_service),
):
    """
    Import an existing team and its members into the specified contest.
    """
    await service.import_team(
        contest_id=contest_id,
        contest_team_import=contest_team_import,
        user_id=user_id,
    )
    logger.info(
        f"Successfully imported team {contest_team_import.team_id} into contest {contest_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=None,
        message="Team imported into contest successfully",
    )


@router.post(
    "/{contest_id}/teams",
    response_model=APIResponse[None],
    summary="Create a new contest team directly in a contest",
)
async def create_contest_team(
    request: Request,
    contest_id: UUID,
    contest_team_create: ContestTeamCreate,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestTeamService = Depends(get_contest_team_service),
):
    """
    Create a new contest team directly in a contest (not in standard teams).
    """
    await service.create_contest_team(
        contest_id=contest_id,
        contest_team_create=contest_team_create,
        user_id=user_id,
    )
    logger.info(
        f"Successfully created contest team {contest_team_create.name} in contest {contest_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=None,
        message="Team created in contest successfully",
    )


@router.patch(
    "/{contest_id}/teams/{contest_team_id}",
    response_model=APIResponse[None],
    summary="Update a contest team",
)
async def update_contest_team(
    request: Request,
    contest_id: UUID,
    contest_team_id: UUID,
    contest_team_update: ContestTeamUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestTeamService = Depends(get_contest_team_service),
):
    """
    Update a contest team.
    """
    await service.update_contest_team(
        contest_team_id=contest_team_id,
        contest_team_update=contest_team_update,
        user_id=user_id,
    )
    logger.info(
        f"Successfully updated team {contest_team_id} in contest {contest_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=None,
        message="Team updated successfully",
    )


@router.patch(
    "/{contest_id}/teams/{contest_team_id}/leader",
    response_model=APIResponse[None],
    summary="Transfer team leadership",
)
async def transfer_contest_team_leader(
    request: Request,
    contest_id: UUID,
    contest_team_id: UUID,
    contest_team_leader_transfer: ContestTeamLeaderTransfer,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestTeamService = Depends(get_contest_team_service),
):
    """
    Transfer team leadership to another member.
    """
    await service.transfer_team_leader(
        contest_team_id=contest_team_id,
        user_id=user_id,
        new_leader_id=contest_team_leader_transfer.new_leader_id,
    )
    logger.info(
        f"Successfully transferred team leadership for team {contest_team_id} in contest {contest_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=None,
        message="Team leadership transferred successfully",
    )


@router.patch(
    "/{contest_id}/teams/{contest_team_id}/status",
    response_model=APIResponse[None],
    summary="Update a contest team status",
)
async def update_contest_team_status(
    request: Request,
    contest_id: UUID,
    contest_team_id: UUID,
    contest_team_status: ContestTeamStatusUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestTeamService = Depends(get_contest_team_service),
):
    """
    Update a contest team status.
    """
    await service.update_contest_team_status(
        contest_team_id=contest_team_id,
        contest_id=contest_id,
        contest_team_status=contest_team_status.status,
        user_id=user_id,
    )
    logger.info(
        f"Successfully updated team status for team {contest_team_id} in contest {contest_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=None,
        message="Team status updated successfully",
    )


@router.patch(
    "/{contest_id}/teams/{contest_team_id}/members/{contest_team_member_id}/status",
    response_model=APIResponse[None],
    summary="Update a contest team member status",
)
async def update_contest_team_member_status(
    request: Request,
    contest_id: UUID,
    contest_team_id: UUID,
    contest_team_member_id: UUID,
    contest_team_member_status_update: ContestTeamMemberStatusUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestTeamService = Depends(get_contest_team_service),
):
    """
    Update a contest team member status.
    """
    await service.update_contest_team_member_status(
        contest_id=contest_id,
        user_id=user_id,
        contest_team_id=contest_team_id,
        contest_team_member_id=contest_team_member_id,
        contest_team_member_status=contest_team_member_status_update.status,
    )
    logger.info(
        f"Successfully updated team member {contest_team_member_id} status for team {contest_team_id} in contest {contest_id}"
    )
    return create_api_response(
        request,
        data=None,
        message="Team member status updated successfully",
    )


@router.patch(
    "/{contest_id}/teams/{contest_team_id}/invitation",
    response_model=APIResponse[None],
    summary="Invite members to a contest team",
)
async def invite_members_to_contest_team(
    request: Request,
    contest_id: UUID,
    contest_team_id: UUID,
    invite_request: ContestTeamInviteRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestTeamService = Depends(get_contest_team_service),
):
    """
    Invite members to a contest team.
    """
    await service.invite_members(
        contest_id=contest_id,
        contest_team_id=contest_team_id,
        invite_user_ids=invite_request.user_ids,
        user_id=user_id,
    )
    logger.info(
        f"Successfully invited members {invite_request.user_ids} to contest team {contest_team_id} in contest {contest_id}"
    )
    return create_api_response(
        request,
        data=None,
        message="Members invited successfully",
    )


@router.post(
    "/{contest_id}/start",
    response_model=APIResponse[ContestTeamProgressResponse],
    summary="Start or resume a contest session for a team",
)
async def start_contest_session(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestService = Depends(get_student_contest_service),
):
    """
    Start or resume a contest session for a team.
    """
    result = await service.start_contest_session(
        contest_id=contest_id,
        user_id=user_id,
    )
    logger.info(
        f"Successfully started/resumed session in contest {contest_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=result,
        message="Contest session started successfully",
    )


@router.get(
    "/{contest_id}/runtime",
    response_model=APIResponse[ContestTeamProgressResponse],
    summary="Get a contest session for a team",
)
async def get_runtime_session(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestService = Depends(get_student_contest_service),
):
    """
    Get a contest session for a team.
    """
    result = await service.get_runtime_session(
        contest_id=contest_id,
        user_id=user_id,
    )
    logger.info(
        f"Successfully fetched session in contest {contest_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=result,
        message="Contest session fetched successfully",
    )


@router.post(
    "/{contest_id}/finish",
    response_model=APIResponse[ContestTeamProgressResponse],
    summary="Finish a contest session for a team",
)
async def finish_contest_session(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestService = Depends(get_student_contest_service),
):
    """
    Finish a contest session for a team.
    """
    result = await service.finish_contest_session(
        contest_id=contest_id,
        user_id=user_id,
    )
    logger.info(
        f"Successfully finished session in contest {contest_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=result,
        message="Contest session finished successfully",
    )


# @router.get(
#     "/{contest_id}/events",
#     summary="Get contest events stream (SSE) for students",
#     response_class=EventSourceResponse,
#     responses={
#         200: {
#             "description": "Server Sent Events stream"
#         }
#     }
# )
# async def get_contest_events_stream(
#     contest_id: UUID,
#     user_id: UUID = Depends(get_current_user_id),
#     service: StudentContestService = Depends(get_student_contest_service),
# ) -> AsyncIterable[ServerSentEvent]:
#     """
#     Establish a Server-Sent Events (SSE) stream for contest lifecycle events on the student side.
#     """
#     try:
#         async for event in service.subscribe_contest_events(contest_id, user_id):
#             yield event
#     except asyncio.CancelledError:
#         logger.info("SSE connection cancelled by client")
