from uuid import UUID

from app.core.cache.decorators import delete_cache_keys
from app.exceptions.submission import InvalidSubmissionScoreError
from app.repositories.contest import ContestRepository
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
    """Service layer for submission reads and instructor/admin score overrides."""

    def __init__(
        self,
        repository: ContestSubmissionRepository,
        contest_repository: ContestRepository,
    ):
        self.repository = repository
        self.contest_repository = contest_repository

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

    async def update_submission_score(
        self, submission_id: UUID, score: int
    ) -> SubmissionDetailResponse:
        """Manually override the score of a single submission.

        Instructors/admins can use this to grade a submission that hasn't
        been auto-evaluated yet, or to override the score of one that has.
        Since a question can have multiple submissions per student, the
        override targets exactly one submission by ID rather than a
        question/student pair. The contest leaderboard is resynced through
        the same live per-member recompute the auto-evaluation pipeline
        uses, so the change is reflected immediately.
        """
        context = await self.repository.get_submission_score_context(submission_id)
        if score > context.max_score:
            raise InvalidSubmissionScoreError(score, context.max_score)

        await self.repository.apply_submission_score(submission_id, score)

        if context.contest_team_member_id is not None:
            await self.contest_repository.recompute_member_score(
                context.contest_id,
                context.contest_team_id,
                context.contest_team_member_id,
            )
            await delete_cache_keys(f"contest:{context.contest_id}:leaderboard*")

        return await self.get_submission_detail(submission_id)
