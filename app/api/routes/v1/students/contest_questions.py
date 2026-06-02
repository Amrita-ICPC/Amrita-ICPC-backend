from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user_id
from app.core.clients.database import get_db
from app.core.clients.redis import get_redis
from app.core.response import create_api_response
from app.repositories.contest import ContestRepository
from app.repositories.contest_runtime import ContestRuntimeRepository
from app.repositories.contest_team_progress import ContestTeamProgressRepository
from app.repositories.student.contest_question import StudentContestQuestionRepository
from app.repositories.student.contest_team import ContestTeamRepository
from app.repositories.testcase import TestCaseRepository
from app.schema.base import APIResponse
from app.schema.student import WorkspaceData, WorkspacePutRequest
from app.schema.student.contests import (
    StudentContestQuestionsListResponse,
    StudentQuestionDetailResponse,
)
from app.schema.student.run import (
    StudentCodeRunRequest,
    StudentCodeRunResponse,
)
from app.service.student.contest_question import StudentContestQuestionService
from app.service.student.workspace import WorkspaceService

router = APIRouter()


def get_student_contest_service(
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
) -> StudentContestQuestionService:
    contest_question_repository = StudentContestQuestionRepository(db)
    contest_repository = ContestRepository(db)
    contest_team_repository = ContestTeamRepository(db)
    contest_team_progress_repository = ContestTeamProgressRepository(db)
    contest_runtime_repository = ContestRuntimeRepository(db)
    testcase_repository = TestCaseRepository(db)
    workspace_service = WorkspaceService(redis_client)
    return StudentContestQuestionService(
        repository=contest_question_repository,
        contest_repository=contest_repository,
        contest_team_repository=contest_team_repository,
        contest_team_progress_repository=contest_team_progress_repository,
        contest_runtime_repository=contest_runtime_repository,
        testcase_repository=testcase_repository,
        workspace_service=workspace_service,
    )


@router.get(
    "/{contest_id}/questions",
    response_model=APIResponse[StudentContestQuestionsListResponse],
    summary="Get questions for a contest",
)
async def get_contest_questions(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestQuestionService = Depends(get_student_contest_service),
):
    """
    Retrieve questions for a contest, ordered by sequence order,
    with attempted/solved status flags.
    """
    result = await service.get_contest_questions(contest_id, user_id)
    return create_api_response(
        request,
        data=result,
        message="Contest questions fetched successfully",
    )


@router.get(
    "/{contest_id}/questions/{question_id}",
    response_model=APIResponse[StudentQuestionDetailResponse],
    summary="Get contest question details for student",
)
async def get_contest_question_details(
    request: Request,
    contest_id: UUID,
    question_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestQuestionService = Depends(get_student_contest_service),
):
    """
    Retrieve details of a specific question in a contest (title, description,
    limits, allowed languages, tags, public testcases, templates) for student preview.
    """
    result = await service.get_contest_question_details(
        contest_id=contest_id, question_id=question_id, user_id=user_id
    )
    return create_api_response(
        request,
        data=result,
        message="Contest question details fetched successfully",
    )


@router.get(
    "/{contest_id}/questions/{question_id}/workspace",
    response_model=APIResponse[WorkspaceData | None],
    summary="Get workspace code for a question",
)
async def get_workspace(
    request: Request,
    contest_id: UUID,
    question_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestQuestionService = Depends(get_student_contest_service),
):
    """
    Retrieve the saved workspace (programming language, source code) for a question.
    """
    result = await service.get_workspace(contest_id, question_id, user_id)
    return create_api_response(
        request,
        data=result,
        message="Workspace fetched successfully",
    )


@router.put(
    "/{contest_id}/questions/{question_id}/workspace",
    response_model=APIResponse[None],
    summary="Save workspace code for a question",
)
async def save_workspace(
    request: Request,
    contest_id: UUID,
    question_id: UUID,
    payload: WorkspacePutRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestQuestionService = Depends(get_student_contest_service),
):
    """
    Save the current code and programming language for a question to the student's/team's workspace.
    """
    await service.save_workspace(
        contest_id=contest_id,
        question_id=question_id,
        user_id=user_id,
        language_id=payload.language_id,
        source_code=payload.source_code,
    )
    return create_api_response(
        request,
        data=None,
        message="Workspace saved successfully",
    )


@router.post(
    "/{contest_id}/questions/{question_id}/run",
    response_model=APIResponse[StudentCodeRunResponse],
    status_code=status.HTTP_200_OK,
    summary="Run student code against sample test cases",
)
async def run_student_code(
    request: Request,
    contest_id: UUID,
    question_id: UUID,
    payload: StudentCodeRunRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestQuestionService = Depends(get_student_contest_service),
):
    """
    Run student code against public (non-hidden) test cases for immediate feedback.
    """
    result = await service.run_code(
        contest_id=contest_id,
        question_id=question_id,
        user_id=user_id,
        code=payload.code,
        language_id=payload.language_id,
    )
    return create_api_response(
        request,
        data=result,
        message="Code execution completed",
    )
