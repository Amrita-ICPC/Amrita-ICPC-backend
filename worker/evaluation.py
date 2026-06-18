"""Celery tasks and helpers for asynchronously evaluating code submissions."""

import asyncio
from uuid import UUID

from app.core.clients.celery import celery_app
from app.core.logger import logger
from worker.evaluation_service import EvaluationService


async def _evaluate_submission_async(submission_id: UUID) -> None:
    """Async helper to evaluate submission using EvaluationService."""
    service = EvaluationService()
    await service.evaluate(submission_id, reevaluation=False, publish_events=True)


async def _evaluate_contest_submission_async(
    contest_id: UUID, evaluation_id: UUID, submission_id: UUID
) -> None:
    """Evaluate a contest submission using EvaluationService."""
    service = EvaluationService()
    context = {"contest_id": contest_id, "evaluation_id": evaluation_id}
    await service.evaluate(
        submission_id,
        reevaluation=True,
        publish_events=False,
        evaluation_context=context,
    )


async def _update_progress_redis(
    contest_id: UUID,
    evaluation_id: UUID,
) -> None:
    """Wrapper to support legacy tests. Delegates to update_evaluation_progress."""
    from worker.redis_helper import update_evaluation_progress

    await update_evaluation_progress(contest_id, evaluation_id)


@celery_app.task
def evaluate_submission(submission_id: UUID | str) -> None:
    """Evaluate submission background task."""
    logger.info(f"Evaluating submission: {submission_id}")
    if isinstance(submission_id, str):
        submission_id = UUID(submission_id)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(_evaluate_submission_async(submission_id))


@celery_app.task
def evaluate_contest_submission(
    contest_id: UUID | str, evaluation_id: UUID | str, submission_id: UUID | str
) -> None:
    """Evaluate a contest submission and update the evaluation progress."""
    logger.info(
        f"Evaluating contest submission: {submission_id} for evaluation: {evaluation_id} in contest: {contest_id}"
    )
    if isinstance(contest_id, str):
        contest_id = UUID(contest_id)
    if isinstance(evaluation_id, str):
        evaluation_id = UUID(evaluation_id)
    if isinstance(submission_id, str):
        submission_id = UUID(submission_id)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(
        _evaluate_contest_submission_async(contest_id, evaluation_id, submission_id)
    )
