from uuid import UUID

from app.repositories.submission import ContestSubmissionRepository
from app.schema.submission import (
    SubmissionDetailLanguageSchema,
    SubmissionDetailQuestionSchema,
    SubmissionDetailResponse,
    SubmissionDetailUserSchema,
    SubmissionTestCaseListResponse,
    SubmissionTestCaseResultSchema,
)


class SubmissionService:
    """Service layer for submission read operations."""

    def __init__(self, repository: ContestSubmissionRepository):
        self.repository = repository

    async def get_submission_detail(
        self, submission_id: UUID
    ) -> SubmissionDetailResponse:
        """Retrieve a submission detail response."""
        row = await self.repository.get_submission_detail(submission_id)
        return SubmissionDetailResponse(
            submission_id=row.submission_id,
            question=SubmissionDetailQuestionSchema(
                id=row.question_id,
                title=row.question_title,
            ),
            submitted_by=SubmissionDetailUserSchema(
                id=row.submitted_by_id,
                name=row.submitted_by_name,
            ),
            status=row.status,
            score=row.score,
            language=SubmissionDetailLanguageSchema(
                id=row.language_id,
                name=row.language_name,
            ),
            submitted_at=row.submitted_at,
            execution_time_ms=row.execution_time_ms,
            memory_kb=row.memory_kb,
            passed_testcases=int(row.passed_testcases or 0),
            total_testcases=int(row.total_testcases or 0),
            source_code=row.source_code,
        )

    async def get_submission_testcases(
        self,
        submission_id: UUID,
        *,
        skip: int,
        limit: int,
    ) -> SubmissionTestCaseListResponse:
        """Retrieve paginated testcase results for a submission."""
        total, rows = await self.repository.get_submission_testcases(
            submission_id,
            skip=skip,
            limit=limit,
        )
        return SubmissionTestCaseListResponse(
            total=total,
            items=[
                SubmissionTestCaseResultSchema(
                    id=row.id,
                    name=f"TC{row.order}",
                    status=row.status,
                    execution_time=row.execution_time,
                    memory=row.memory,
                    input=row.input,
                    expected_output=row.expected_output,
                    actual_output=row.actual_output,
                )
                for row in rows
            ],
        )
