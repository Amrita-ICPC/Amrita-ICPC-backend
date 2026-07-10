import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache.decorators import delete_cache_keys
from app.core.clients.database import SessionLocal
from app.core.config import config
from app.core.logger import logger
from app.exceptions.judge0 import (
    Judge0ConnectionError,
    Judge0ServiceUnavailableError,
    Judge0TimeoutError,
)
from app.models.contest import ContestSubmission, ContestTeam
from app.models.question import Submission, SubmissionTestCase
from app.repositories.contest import ContestRepository
from app.repositories.dto.evaluation import EvaluationResult
from app.repositories.dto.judge0 import Judge0ExecutionRequestDTO
from app.repositories.question import QuestionRepository
from app.schema.evaluation import (
    ContestSubmissionContext,
    EvalRef,
    EvaluationPreparationDetails,
    SubmissionPendingContext,
    TokenEntry,
)
from app.schema.question import (
    QuestionAndTestcasesResponse,
    QuestionTestCaseResponse,
)
from app.service.contest_event_service import ContestEventService
from app.utils.enums import SubmissionStatus
from app.utils.evaluation import calculate_submission_score
from app.validators.question import QuestionValidator
from worker.judge0_service import Judge0EvaluationService
from worker.redis_helper import (
    clear_pending,
    get_submission_context,
    is_evaluation_valid,
    is_pending,
    register_pending,
    release_contest_slot,
    release_inflight,
    try_acquire_contest_slot,
    try_acquire_inflight,
    update_evaluation_progress,
)


class BackpressureError(Exception):
    """Raised when backpressure caps prevent admitting a submission right now.

    The Celery task layer catches this and retries the SUBMIT task after a short
    countdown, so the submission is admitted once capacity frees up.
    """


class EvaluationService:
    """Service to manage the fetching, execution orchestration, and saving of submission evaluations."""

    def __init__(self) -> None:
        self.judge0_service = Judge0EvaluationService()

    async def _get_contest_submission_context(
        self, db: AsyncSession, submission_id: UUID
    ) -> ContestSubmissionContext | None:
        """Fetch the contest submission context via a direct SELECT, avoiding ORM lazy-loading.

        Args:
            db: The async database session.
            submission_id: UUID of the submission to look up.

        Returns:
            ContestSubmissionContext if the submission belongs to a contest, otherwise None.
        """
        stmt = (
            select(
                ContestSubmission.contest_id,
                ContestSubmission.contest_team_id,
                ContestSubmission.contest_team_member_id,
                ContestTeam.team_id,
            )
            .join(ContestTeam, ContestTeam.id == ContestSubmission.contest_team_id)
            .where(ContestSubmission.submission_id == submission_id)
        )
        res = await db.execute(stmt)
        row = res.first()
        if row:
            return ContestSubmissionContext(
                contest_id=row.contest_id,
                team_id=row.team_id,
                contest_team_id=row.contest_team_id,
                contest_team_member_id=row.contest_team_member_id,
            )
        return None

    async def get_question_and_testcases(
        self, db: AsyncSession, question_id: UUID
    ) -> QuestionAndTestcasesResponse:
        """
        Fetch the question and its associated testcases from the database.

        Args:
            db: AsyncSession database session.
            question_id: UUID of the question to retrieve.

        Returns:
            QuestionAndTestcasesResponse: A Pydantic model containing the question,
                                          testcases, and templates for evaluation.
        """
        repository = QuestionRepository(db)
        question = await repository.get_question_or_raise(question_id)
        return QuestionAndTestcasesResponse.from_question_and_testcases(
            question, list(question.testcases)
        )

    async def cleanup_submission(
        self,
        db: AsyncSession,
        repository: QuestionRepository,
        submission_id: UUID,
        submission: Submission,
    ) -> None:
        """Reset evaluation status and clean up old testcase results from the database."""
        submission.is_evaluated = False
        testcase_exists_result = await db.execute(
            select(SubmissionTestCase.id)
            .filter(SubmissionTestCase.submission_id == submission_id)
            .limit(1)
        )
        has_testcases = testcase_exists_result.scalar_one_or_none() is not None

        if has_testcases:
            await repository.delete_submission_testcases_batch(submission_id)

        await db.commit()

    async def prepare_evaluation(
        self,
        db: AsyncSession,
        submission_id: UUID,
        reevaluation: bool = False,
    ) -> EvaluationPreparationDetails | None:
        """
        Prepare details for submission evaluation.

        Args:
            db: AsyncSession database session.
            submission_id: UUID of the submission to evaluate.
            reevaluation: If True, resets evaluated status and deletes old testcase results.
                          If False, aborts if the submission has already been evaluated.

        Returns:
            EvaluationPreparationDetails: Pydantic model containing the submission, testcases,
                                          source code, and context, or None if aborted.
        """
        repository = QuestionRepository(db)

        # 1. Fetch submission
        submission = await repository.get_submission(submission_id)
        if submission is None:
            logger.error(f"Submission not found: {submission_id}")
            return None

        if reevaluation:
            await self.cleanup_submission(db, repository, submission_id, submission)
        else:
            # Ensure it hasn't been evaluated already
            if submission.is_evaluated:
                logger.warning(
                    f"Submission {submission_id} is already evaluated, aborting evaluation."
                )
                return None

        # Build context for SSE updates
        contest_submission_context = await self._get_contest_submission_context(
            db, submission_id
        )

        # 2. Fetch question and testcases
        data = await self.get_question_and_testcases(db, submission.question_id)
        testcases = data.testcases

        template = QuestionValidator.validate_submission_language(
            data, submission.language_id
        )

        # Compute capped execution limits from the problem definition.
        cpu, wall, mem_kb, stack_kb = self._compute_limits(
            data.time_limit_ms, data.memory_limit_mb
        )

        if not testcases:
            logger.warning(f"No testcases found for question {data.id}")
            return EvaluationPreparationDetails(
                submission=submission,
                testcases=[],
                final_source_code="",
                max_score=0,
                cpu_time_limit=cpu,
                wall_time_limit=wall,
                memory_limit=mem_kb,
                stack_limit=stack_kb,
                contest_submission_context=contest_submission_context,
            )

        # 3. Form final source code
        final_source_code = submission.source_code
        if template and template.driver_code:
            final_source_code = f"{submission.source_code}\n\n{template.driver_code}"

        # 4. Get max score
        max_score = 100
        if contest_submission_context:
            contest_id = contest_submission_context.contest_id
            contest_question_score = await repository.get_contest_question_score(
                contest_id, submission.question_id
            )
            if contest_question_score is not None:
                max_score = contest_question_score

        return EvaluationPreparationDetails(
            submission=submission,
            testcases=testcases,
            final_source_code=final_source_code,
            max_score=max_score,
            cpu_time_limit=cpu,
            wall_time_limit=wall,
            memory_limit=mem_kb,
            stack_limit=stack_kb,
            contest_submission_context=contest_submission_context,
        )

    @staticmethod
    def _compute_limits(
        time_limit_ms: int, memory_limit_mb: int
    ) -> tuple[float, float, int, int]:
        """Derive Judge0 execution limits from a problem's configured limits.

        Per-problem values are used when present, otherwise config defaults; both
        are then clamped by the global safety caps so a misconfigured problem can
        never request unbounded resources.

        Args:
            time_limit_ms: Problem CPU time limit in milliseconds (0 if unset).
            memory_limit_mb: Problem memory limit in megabytes (0 if unset).

        Returns:
            Tuple of ``(cpu_time_s, wall_time_s, memory_kb, stack_kb)``.
        """
        cpu = (
            time_limit_ms / 1000.0
            if time_limit_ms and time_limit_ms > 0
            else config.JUDGE0_DEFAULT_CPU_TIME
        )
        cpu = min(cpu, config.JUDGE0_MAX_CPU_TIME)

        wall = min(cpu * config.JUDGE0_WALL_TIME_FACTOR, config.JUDGE0_MAX_WALL_TIME)

        mem_kb = (
            memory_limit_mb * 1024
            if memory_limit_mb and memory_limit_mb > 0
            else config.JUDGE0_DEFAULT_MEMORY_KB
        )
        mem_kb = min(mem_kb, config.JUDGE0_MAX_MEMORY_KB)
        # Judge0 rejects memory_limit below this floor with a 422; a small
        # per-problem memory_limit_mb (e.g. 1) must not be sent as-is.
        mem_kb = max(mem_kb, config.JUDGE0_MIN_MEMORY_KB)

        return cpu, wall, mem_kb, config.JUDGE0_STACK_LIMIT_KB

    async def save_result(
        self,
        db: AsyncSession,
        submission_id: UUID,
        eval_result: EvaluationResult,
        testcases: list[QuestionTestCaseResponse],
        max_score: int,
    ) -> Submission | None:
        """Save evaluation result in database."""
        score = calculate_submission_score(
            max_score, testcases, eval_result.testcase_results
        )

        repository = QuestionRepository(db)
        submission = await repository.get_submission(submission_id)
        if submission is None:
            logger.error(f"Submission not found during save phase: {submission_id}")
            return None

        # Re-associate the testcase result objects with the fresh session's submission
        for stc in eval_result.testcase_results:
            stc.submission = submission
            stc.submission_id = submission.id

        submission.score = score
        await repository.complete_submission(submission, eval_result)
        await db.commit()
        return submission

    async def _sync_team_progress_score(
        self,
        db: AsyncSession,
        contest_sub_ctx: ContestSubmissionContext,
    ) -> None:
        """Refresh one contest team member's live leaderboard score.

        Called right after a submission's score/evaluated state is committed
        by ``save_result``, so ``ContestTeamProgress.score`` stays live
        without an admin needing to trigger the contest-wide "compute
        scores" endpoint. Scoped to the single member who submitted, via
        ``ContestRepository.recompute_member_score`` - see that method for
        why this is safe under concurrent submissions (it's one atomic
        UPDATE, naturally serialized by Postgres's row lock).

        Best-effort: the submission itself is already durably finalized by
        the time this runs, so a failure here (e.g. a transient DB error)
        must not be allowed to unwind or reclassify that already-committed
        result. Errors are logged and swallowed; the next evaluation for
        this member (or a manual recompute) will catch the score up.

        Also busts the cached leaderboard for this contest so the DB write
        is actually visible to instructors/admins right away. Without this,
        ``GET /contests/{id}/leaderboard`` keeps serving its cached response
        (up to 300s old) even though the underlying row already changed -
        which is what made bulk-evaluation score updates look like they
        "weren't happening" while a run was still in progress.

        Args:
            db: Async session to run the sync on (reused from PERSIST).
            contest_sub_ctx: Context identifying the contest/team/member.
        """
        if (
            contest_sub_ctx.contest_team_id is None
            or contest_sub_ctx.contest_team_member_id is None
        ):
            return
        try:
            await ContestRepository(db).recompute_member_score(
                contest_sub_ctx.contest_id,
                contest_sub_ctx.contest_team_id,
                contest_sub_ctx.contest_team_member_id,
            )
            await db.commit()
            await delete_cache_keys(
                f"contest:{contest_sub_ctx.contest_id}:leaderboard*"
            )
        except Exception as e:
            logger.error(
                f"Failed to sync contest team progress score "
                f"(contest={contest_sub_ctx.contest_id}, "
                f"member={contest_sub_ctx.contest_team_member_id}): {e}"
            )
            await db.rollback()

    async def _publish_student_event(
        self,
        event_service: ContestEventService,
        submission_id: UUID,
        question_id: UUID,
        contest_submission_context: ContestSubmissionContext | None,
        status: str,
        score: int | None = None,
        passed_testcases: int | None = None,
        total_testcases: int | None = None,
    ) -> None:
        """Publish submission status update event to the contest event publisher for students.

        score/passed_testcases/total_testcases are only known once a terminal
        verdict has been persisted (see save_result/persist); left as None for
        the "RUNNING" event fired right after submit. Root cause of "score
        never updates" for a client that renders straight off this SSE push
        instead of re-fetching the submission: this event previously carried
        only a bare status string, never the score itself, even though the DB
        row had already been updated correctly by the time this fires.
        """
        if not contest_submission_context:
            return
        contest_id = contest_submission_context.contest_id
        team_id = contest_submission_context.team_id
        contest_team_member_id = contest_submission_context.contest_team_member_id
        if contest_id and team_id and contest_team_member_id:
            from app.schema.student.submission import (
                StudentSubmissionUpdateEvent,
                StudentSubmissionUpdatePayload,
            )

            event = StudentSubmissionUpdateEvent(
                type="submission_update",
                payload=StudentSubmissionUpdatePayload(
                    submission_id=str(submission_id),
                    question_id=str(question_id),
                    status=status,
                    score=score,
                    passed_testcases=passed_testcases,
                    total_testcases=total_testcases,
                ),
            )
            await event_service.publish_event(
                contest_id, team_id, contest_team_member_id, event
            )

    # ----------------------------------------------------------------- #
    # Stage helpers                                                      #
    # ----------------------------------------------------------------- #
    async def _advance_progress(
        self,
        eval_contest_id: UUID | None,
        evaluation_id: UUID | None,
        submission_id: UUID,
    ) -> None:
        """Advance bulk-evaluation progress, if this submission belongs to one."""
        if eval_contest_id and evaluation_id:
            await update_evaluation_progress(
                eval_contest_id, evaluation_id, submission_id
            )

    async def _persist_terminal_status(
        self,
        submission_id: UUID,
        question_id: UUID | None,
        status: SubmissionStatus,
        contest_sub_ctx: ContestSubmissionContext | None,
        publish_events: bool,
        event_service: ContestEventService,
    ) -> None:
        """Write a terminal verdict with no testcase rows and publish it.

        Used for early-exit cases: no testcases (AC), total submit failure or a
        load/validation error (SYSTEM_ERROR). This is a single, terminal DB write.

        Args:
            submission_id: Submission to finalize.
            question_id: Question id (for the SSE event payload).
            status: Terminal verdict to record.
            contest_sub_ctx: SSE context, or None for non-contest submissions.
            publish_events: Whether to emit an SSE status event.
            event_service: Publisher used for SSE events.
        """
        async with SessionLocal() as db:
            repository = QuestionRepository(db)
            sub = await repository.get_submission(submission_id)
            if sub is None:
                return
            if sub.is_evaluated:
                return  # Idempotent: already finalized by a concurrent worker.
            result = EvaluationResult(
                status=status,
                passed_testcases=0,
                total_testcases=0,
                total_time=0,
                total_memory=0,
                testcase_results=[],
            )
            sub.score = 0
            await repository.complete_submission(sub, result)
            await db.commit()
            resolved_question_id = question_id or sub.question_id

        if publish_events:
            await self._publish_student_event(
                event_service,
                submission_id,
                resolved_question_id,
                contest_sub_ctx,
                status.value,
                score=0,
                passed_testcases=0,
                total_testcases=0,
            )

    # ----------------------------------------------------------------- #
    # SUBMIT stage                                                       #
    # ----------------------------------------------------------------- #
    async def submit(
        self,
        submission_id: UUID,
        reevaluation: bool = False,
        publish_events: bool = True,
        evaluation_context: EvalRef | None = None,
    ) -> None:
        """Submit a submission's testcases to Judge0 and register it for polling.

        This is a *fast* stage: it loads the submission, batch-submits every
        testcase to Judge0, stores the resulting token map in Redis and returns.
        No worker is held polling — the Beat poller collects results later. All
        transient state lives in Redis; the database is untouched until PERSIST
        (except for the early-exit terminal cases below).

        Args:
            submission_id: Submission to evaluate.
            reevaluation: If True, clears any prior result first.
            publish_events: Whether to emit SSE status events (student path).
            evaluation_context: Present for bulk contest evaluation; carries the
                contest and evaluation ids used for supersede checks and progress.

        Raises:
            BackpressureError: If global or per-contest in-flight caps are hit; the
                task layer retries after a short countdown.
        """
        event_service = ContestEventService()
        eval_contest_id = evaluation_context.contest_id if evaluation_context else None
        evaluation_id = evaluation_context.evaluation_id if evaluation_context else None

        # Skip work for superseded/completed bulk evaluations.
        if eval_contest_id and evaluation_id:
            if not await is_evaluation_valid(
                eval_contest_id, evaluation_id, submission_id
            ):
                return

        # Idempotency guard: a redelivered task (worker crashed/killed after an
        # earlier attempt already reached register_pending) must not re-acquire
        # gates and re-submit to Judge0. The first attempt is already tracked in
        # Redis and will be collected by the poller, so this redelivery is a
        # no-op.
        if await is_pending(submission_id):
            logger.info(
                f"Submission {submission_id} is already pending collection; "
                f"skipping duplicate SUBMIT dispatch."
            )
            return

        async def _terminal_exit(
            question_id: UUID | None,
            status: SubmissionStatus,
            contest_sub_ctx: ContestSubmissionContext | None,
        ) -> None:
            """Record a terminal verdict and advance bulk progress, then return."""
            await self._persist_terminal_status(
                submission_id,
                question_id,
                status,
                contest_sub_ctx,
                publish_events,
                event_service,
            )
            await self._advance_progress(eval_contest_id, evaluation_id, submission_id)

        # --- Load & validate (short DB session) ---
        async with SessionLocal() as db:
            try:
                prep = await self.prepare_evaluation(
                    db, submission_id, reevaluation=reevaluation
                )
            except Exception as e:
                logger.error(
                    f"Validation/load failed for submission {submission_id}: {e}"
                )
                await db.rollback()
                prep = None
                load_failed = True
            else:
                load_failed = False

        if not load_failed and prep is None:
            # Already evaluated / not found — nothing to do.
            await self._advance_progress(eval_contest_id, evaluation_id, submission_id)
            return

        # --- Load/validation error: record terminal SYSTEM_ERROR ---
        if load_failed:
            async with SessionLocal() as ctx_db:
                contest_sub_ctx = await self._get_contest_submission_context(
                    ctx_db, submission_id
                )
            await _terminal_exit(None, SubmissionStatus.SYSTEM_ERROR, contest_sub_ctx)
            return

        # --- No testcases: immediate terminal AC ---
        if not prep.testcases:
            await _terminal_exit(
                prep.submission.question_id,
                SubmissionStatus.AC,
                prep.contest_submission_context,
            )
            return

        # --- Backpressure gates ---
        if not await try_acquire_inflight(config.JUDGE0_MAX_INFLIGHT):
            raise BackpressureError("Global Judge0 in-flight cap reached")

        acquired_contest = False
        if eval_contest_id and evaluation_id:
            acquired_contest = await try_acquire_contest_slot(
                eval_contest_id,
                evaluation_id,
                config.EVAL_MAX_ACTIVE_TASKS_PER_CONTEST,
            )
            if not acquired_contest:
                await release_inflight()
                raise BackpressureError("Per-contest active cap reached")

        async def _release_gates() -> None:
            await release_inflight()
            if acquired_contest:
                await release_contest_slot(eval_contest_id, evaluation_id)

        # --- Batch submit to Judge0 and register for polling ---
        # Kept in one try/except: any failure here (including a hung call hitting
        # the Celery soft time limit) must release the gates just acquired above
        # and record a terminal verdict, or the submission is stuck forever with
        # leaked capacity.
        try:
            request_dto = Judge0ExecutionRequestDTO(
                question_id=str(prep.submission.question_id),
                source_code=prep.final_source_code,
                language_id=prep.submission.language_id,
                cpu_time_limit=prep.cpu_time_limit,
                wall_time_limit=prep.wall_time_limit,
                memory_limit=prep.memory_limit,
                stack_limit=prep.stack_limit,
            )
            tokens = await self.judge0_service.submit_testcases(
                request_dto, prep.testcases
            )

            if all(token is None for token in tokens):
                raise RuntimeError("Judge0 batch submit returned no usable tokens")

            deadline = time.time() + config.EVAL_SUBMISSION_DEADLINE_SECONDS
            pending_context = SubmissionPendingContext(
                submission_id=submission_id,
                question_id=prep.submission.question_id,
                max_score=prep.max_score,
                reevaluation=reevaluation,
                publish_events=publish_events,
                tokens=[
                    TokenEntry(token=token, testcase_id=testcase.id)
                    for testcase, token in zip(prep.testcases, tokens)
                ],
                eval_ref=(
                    EvalRef(contest_id=eval_contest_id, evaluation_id=evaluation_id)
                    if eval_contest_id and evaluation_id
                    else None
                ),
                sse=prep.contest_submission_context,
                deadline=deadline,
            )
            await register_pending(submission_id, pending_context, deadline)
        except (
            Judge0TimeoutError,
            Judge0ConnectionError,
            Judge0ServiceUnavailableError,
        ) as e:
            # Transient Judge0-side failure (timeout/connection/503): release the
            # gates just acquired and let the task layer retry with backoff,
            # rather than permanently failing a submission over a blip.
            logger.warning(
                f"Transient Judge0 failure for submission {submission_id}; "
                f"releasing gates for retry: {e}"
            )
            await _release_gates()
            raise
        except Exception as e:
            logger.error(f"SUBMIT failed for submission {submission_id}: {e}")
            await _release_gates()
            # Record terminal SYSTEM_ERROR so the submission is not stuck forever.
            await _terminal_exit(
                prep.submission.question_id,
                SubmissionStatus.SYSTEM_ERROR,
                prep.contest_submission_context,
            )
            return

        if publish_events:
            await self._publish_student_event(
                event_service,
                submission_id,
                prep.submission.question_id,
                prep.contest_submission_context,
                "RUNNING",
            )

    async def submit_give_up(
        self,
        submission_id: UUID,
        publish_events: bool,
        evaluation_context: EvalRef | None,
    ) -> None:
        """Record terminal SYSTEM_ERROR once the transient-Judge0 retry budget is spent.

        Called by the task layer when ``submit`` has raised a transient Judge0
        error (timeout/connection/503) more times than
        ``config.JUDGE0_TRANSIENT_MAX_RETRIES``. The backpressure gates were
        already released in ``submit`` the moment the transient error was first
        caught, so this only needs to write the terminal verdict and advance
        bulk progress.

        Args:
            submission_id: Submission to finalize.
            publish_events: Whether to emit an SSE status event.
            evaluation_context: Bulk-evaluation ids, if applicable.
        """
        eval_contest_id = evaluation_context.contest_id if evaluation_context else None
        evaluation_id = evaluation_context.evaluation_id if evaluation_context else None
        async with SessionLocal() as db:
            contest_sub_ctx = await self._get_contest_submission_context(
                db, submission_id
            )
        await self._persist_terminal_status(
            submission_id,
            None,
            SubmissionStatus.SYSTEM_ERROR,
            contest_sub_ctx,
            publish_events,
            ContestEventService(),
        )
        await self._advance_progress(eval_contest_id, evaluation_id, submission_id)

    # ----------------------------------------------------------------- #
    # PERSIST stage                                                      #
    # ----------------------------------------------------------------- #
    async def persist(self, submission_id: UUID, timed_out: bool = False) -> None:
        """Collect Judge0 results for a submission and write the terminal verdict.

        Re-fetches results for the submission's tokens, aggregates them, scores
        the submission and writes the single terminal DB transition. Idempotent:
        a second invocation (e.g. a retried poller dispatch) is a no-op once the
        submission is evaluated. Always releases the in-flight gates and clears
        the Redis working state.

        Args:
            submission_id: Submission to finalize.
            timed_out: When True, unresolved testcases are recorded as TLE because
                the submission exceeded its deadline.
        """
        event_service = ContestEventService()
        context = await get_submission_context(submission_id)
        if context is None:
            # Nothing to persist (already finalized or context expired).
            return

        eval_contest_id = context.eval_ref.contest_id if context.eval_ref else None
        evaluation_id = context.eval_ref.evaluation_id if context.eval_ref else None
        publish_events = context.publish_events
        max_score = context.max_score
        question_id = context.question_id
        contest_sub_ctx = context.sse
        token_entries = context.tokens

        async def _cleanup() -> None:
            """Release gates and clear transient Redis state for this submission."""
            await clear_pending(submission_id)
            await release_inflight()
            if eval_contest_id and evaluation_id:
                await release_contest_slot(eval_contest_id, evaluation_id)

        # Supersede guard for bulk evaluation.
        if eval_contest_id and evaluation_id:
            if not await is_evaluation_valid(
                eval_contest_id, evaluation_id, submission_id
            ):
                await _cleanup()
                return

        try:
            # Fetch all available Judge0 results for this submission's tokens.
            tokens = [entry.token for entry in token_entries]
            valid_tokens = [t for t in tokens if t]
            results_by_token = await self.judge0_service.judge0_repo.get_batch_results(
                valid_tokens
            )

            async with SessionLocal() as db:
                repository = QuestionRepository(db)
                submission = await repository.get_submission(submission_id)
                if submission is None:
                    # Stall-avoidance: cleanup/progress run in the finally block so
                    # the bulk run can still complete. (release happens once.)
                    logger.error(f"Submission {submission_id} missing at persist.")
                    return
                if submission.is_evaluated:
                    # Idempotent: another worker already finalized this submission.
                    # Cleanup runs in finally; progress is exactly-once via SADD.
                    return

                # Reload testcases (for weights/scoring) and align with tokens.
                data = await self.get_question_and_testcases(db, question_id)
                tc_by_id = {tc.id: tc for tc in data.testcases}
                aligned_testcases = [
                    tc_by_id[entry.testcase_id]
                    for entry in token_entries
                    if entry.testcase_id in tc_by_id
                ]
                aligned_tokens = [
                    entry.token
                    for entry in token_entries
                    if entry.testcase_id in tc_by_id
                ]

                eval_result = self.judge0_service.build_evaluation_result(
                    submission_id,
                    aligned_testcases,
                    aligned_tokens,
                    results_by_token,
                    timed_out=timed_out,
                )

                finalized_submission = await self.save_result(
                    db, submission_id, eval_result, data.testcases, max_score
                )

                if contest_sub_ctx is not None:
                    await self._sync_team_progress_score(db, contest_sub_ctx)

            status_str = (
                eval_result.status.value if eval_result.status else "SYSTEM_ERROR"
            )
            if publish_events:
                await self._publish_student_event(
                    event_service,
                    submission_id,
                    question_id,
                    contest_sub_ctx,
                    status_str,
                    score=(
                        finalized_submission.score
                        if finalized_submission is not None
                        else None
                    ),
                    passed_testcases=eval_result.passed_testcases,
                    total_testcases=eval_result.total_testcases,
                )
            logger.info(
                f"Finished evaluation for submission {submission_id} "
                f"with status {status_str}"
            )
        except Exception as e:
            # Never leave a submission without a terminal verdict: a Judge0/DB
            # failure during PERSIST is recorded as SYSTEM_ERROR so the row is
            # final and (for bulk) the run can complete. Cleanup/progress run in
            # the finally block.
            logger.error(
                f"PERSIST failed for submission {submission_id}: {e}", exc_info=True
            )
            try:
                await self._persist_terminal_status(
                    submission_id,
                    question_id,
                    SubmissionStatus.SYSTEM_ERROR,
                    contest_sub_ctx,
                    publish_events,
                    event_service,
                )
            except Exception:
                logger.error(
                    f"Failed to record terminal SYSTEM_ERROR for {submission_id}"
                )
        finally:
            await _cleanup()
            await self._advance_progress(eval_contest_id, evaluation_id, submission_id)
