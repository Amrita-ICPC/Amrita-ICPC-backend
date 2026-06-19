from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import can_read
from app.core.clients.database import get_db
from app.core.response import create_api_response
from app.repositories.submission import ContestSubmissionRepository
from app.schema.base import APIResponse
from app.schema.submission import (
    SubmissionDetailResponse,
    SubmissionTestCaseListResponse,
)
from app.service.submission_service import SubmissionService
from app.utils.pagination import get_pagination

router = APIRouter()


def get_submission_service(db: AsyncSession = Depends(get_db)) -> SubmissionService:
    """Dependency injector for submission reads."""
    return SubmissionService(repository=ContestSubmissionRepository(db))


@router.get(
    "/{submission_id}",
    response_model=APIResponse[SubmissionDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="Get submission detail",
    dependencies=[can_read("contests")],
)
async def get_submission_detail(
    request: Request,
    submission_id: UUID,
    service: SubmissionService = Depends(get_submission_service),
) -> APIResponse[SubmissionDetailResponse]:
    """Get full details for a single submission."""
    submission = await service.get_submission_detail(submission_id)
    return create_api_response(
        request,
        data=submission,
        message="Submission fetched successfully",
        status_code=status.HTTP_200_OK,
    )


@router.get(
    "/{submission_id}/testcases",
    response_model=APIResponse[SubmissionTestCaseListResponse],
    status_code=status.HTTP_200_OK,
    summary="Get submission testcase results",
    dependencies=[can_read("contests")],
)
async def get_submission_testcases(
    request: Request,
    submission_id: UUID,
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(
        10, ge=1, le=100, description="Number of testcases per page"
    ),
    service: SubmissionService = Depends(get_submission_service),
) -> APIResponse[SubmissionTestCaseListResponse]:
    """Get paginated testcase results for a submission."""
    skip = (page - 1) * page_size
    testcases = await service.get_submission_testcases(
        submission_id,
        skip=skip,
        limit=page_size,
    )
    pagination = get_pagination(total=testcases.total, page=page, page_size=page_size)
    return create_api_response(
        request,
        data=testcases,
        message="Submission testcases fetched successfully",
        status_code=status.HTTP_200_OK,
        pagination=pagination,
    )
