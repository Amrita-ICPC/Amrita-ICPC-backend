from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user_id
from app.core.clients.database import get_db
from app.core.response import create_api_response
from app.repositories.student.contest import StudentContestRepository
from app.repositories.dto.pagination import PaginationParams
from app.schema.base import APIResponse
from app.schema.student.contests import StudentContestRegistrationRequest, StudentContestListResponse
from app.service.student.contests import StudentContestService
from app.utils.pagination import get_pagination

router = APIRouter()


def get_student_contest_service(
    db: AsyncSession = Depends(get_db),
) -> StudentContestService:
    repository = StudentContestRepository(db)
    return StudentContestService(repository)


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
