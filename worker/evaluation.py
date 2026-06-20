"""Celery tasks for the staged, token-polling evaluation pipeline.

The pipeline is split into independent, short-lived stages so that no worker is
ever blocked polling Judge0:

- :func:`submit_evaluation`  — SUBMIT: batch-submit to Judge0, store tokens, return.
- :func:`poll_pending_evaluations` (in :mod:`worker.poller`) — POLL: one Beat task
  batch-collects results and dispatches PERSIST.
- :func:`persist_evaluation` — PERSIST: aggregate, score, write the terminal verdict.

The legacy task names (:func:`evaluate_submission`,
:func:`evaluate_contest_submission`) are kept as thin shims that route into the
staged flow so existing callers keep working.
"""

import asyncio
from uuid import UUID

from app.core.clients.celery import celery_app
from app.core.config import config
from app.core.logger import logger
from app.exceptions.judge0 import (
    Judge0ConnectionError,
    Judge0ServiceUnavailableError,
    Judge0TimeoutError,
)
from app.schema.evaluation import EvalRef
from worker.evaluation_service import BackpressureError, EvaluationService


def _run(coro) -> None:
    """Run a coroutine to completion on the worker's event loop."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(coro)


def _eval_context(contest_id: str | None, evaluation_id: str | None) -> EvalRef | None:
    """Build a typed evaluation reference from optional id strings."""
    if contest_id and evaluation_id:
        return EvalRef(contest_id=UUID(contest_id), evaluation_id=UUID(evaluation_id))
    return None


# --------------------------------------------------------------------------- #
# SUBMIT stage                                                                #
# --------------------------------------------------------------------------- #
@celery_app.task(bind=True, max_retries=None)
def submit_evaluation(
    self,
    submission_id: str,
    reevaluation: bool = False,
    publish_events: bool = True,
    contest_id: str | None = None,
    evaluation_id: str | None = None,
    judge0_retry_count: int = 0,
) -> None:
    """SUBMIT stage: push a submission's testcases to Judge0 and register polling.

    Retries (with a short countdown) when backpressure caps are hit, so the
    submission is admitted once capacity frees up rather than overrunning Judge0.
    Also retries, with exponential backoff up to a bounded budget, on transient
    Judge0 failures (timeout/connection/503) rather than immediately failing the
    submission over a blip.

    Args:
        submission_id: Submission to evaluate.
        reevaluation: If True, clears any prior result first.
        publish_events: Whether to emit SSE status events.
        contest_id: Bulk-evaluation contest id (None for live student submits).
        evaluation_id: Bulk-evaluation run id (None for live student submits).
        judge0_retry_count: Number of transient-Judge0-failure retries so far.
            Tracked separately from Celery's own retry counter so backpressure
            retries (unbounded) don't eat into this bounded budget.
    """
    logger.info(f"SUBMIT stage for submission: {submission_id}")
    service = EvaluationService()
    context = _eval_context(contest_id, evaluation_id)
    try:
        _run(
            service.submit(
                UUID(submission_id),
                reevaluation=reevaluation,
                publish_events=publish_events,
                evaluation_context=context,
            )
        )
    except BackpressureError as exc:
        logger.info(f"Backpressure for submission {submission_id}; retrying: {exc}")
        raise self.retry(countdown=config.EVAL_BACKPRESSURE_RETRY_SECONDS, exc=exc)
    except (
        Judge0TimeoutError,
        Judge0ConnectionError,
        Judge0ServiceUnavailableError,
    ) as exc:
        if judge0_retry_count >= config.JUDGE0_TRANSIENT_MAX_RETRIES:
            logger.error(
                f"Judge0 still unavailable after {judge0_retry_count} retries for "
                f"submission {submission_id}; giving up with SYSTEM_ERROR: {exc}"
            )
            _run(
                service.submit_give_up(
                    UUID(submission_id),
                    publish_events=publish_events,
                    evaluation_context=context,
                )
            )
            return
        countdown = min(
            5 * (2**judge0_retry_count),
            config.JUDGE0_TRANSIENT_RETRY_MAX_BACKOFF_SECONDS,
        )
        logger.warning(
            f"Transient Judge0 failure for submission {submission_id}; "
            f"retrying in {countdown}s (attempt {judge0_retry_count + 1}): {exc}"
        )
        raise self.retry(
            countdown=countdown,
            exc=exc,
            kwargs={
                "submission_id": submission_id,
                "reevaluation": reevaluation,
                "publish_events": publish_events,
                "contest_id": contest_id,
                "evaluation_id": evaluation_id,
                "judge0_retry_count": judge0_retry_count + 1,
            },
        )


# --------------------------------------------------------------------------- #
# PERSIST stage                                                               #
# --------------------------------------------------------------------------- #
@celery_app.task
def persist_evaluation(submission_id: str, timed_out: bool = False) -> None:
    """PERSIST stage: collect Judge0 results and write the terminal verdict.

    Args:
        submission_id: Submission to finalize.
        timed_out: When True, unresolved testcases are recorded as TLE because the
            submission exceeded its polling deadline.
    """
    logger.info(
        f"PERSIST stage for submission: {submission_id} (timed_out={timed_out})"
    )
    service = EvaluationService()
    _run(service.persist(UUID(submission_id), timed_out=timed_out))


# --------------------------------------------------------------------------- #
# Legacy compatibility shims (delegate to the staged flow)                    #
# --------------------------------------------------------------------------- #
@celery_app.task
def evaluate_submission(submission_id: UUID | str) -> None:
    """Deprecated: delegates to the staged SUBMIT flow for a student submission."""
    service = EvaluationService()
    _run(
        service.submit(
            UUID(str(submission_id)),
            reevaluation=False,
            publish_events=True,
            evaluation_context=None,
        )
    )


@celery_app.task
def evaluate_contest_submission(
    contest_id: UUID | str, evaluation_id: UUID | str, submission_id: UUID | str
) -> None:
    """Deprecated: delegates to the staged SUBMIT flow for a bulk evaluation."""
    service = EvaluationService()
    context = EvalRef(
        contest_id=UUID(str(contest_id)), evaluation_id=UUID(str(evaluation_id))
    )
    _run(
        service.submit(
            UUID(str(submission_id)),
            reevaluation=True,
            publish_events=False,
            evaluation_context=context,
        )
    )
