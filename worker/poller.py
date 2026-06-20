"""Central Beat poller that collects Judge0 results for pending submissions.

A single periodic task (scheduled via Celery Beat) batch-fetches results for
every in-flight submission's tokens in as few Judge0 calls as possible, then
dispatches the PERSIST stage for submissions whose tokens are all terminal or
whose deadline has elapsed. Running this as one shared task — instead of one
polling task per submission — is what keeps the worker pool free at 500-1000
concurrent submissions.

The task guards itself with a Redis lock so overlapping Beat ticks (or redundant
Beat instances) never double-poll.
"""

import asyncio
import time

from app.core.clients.celery import celery_app
from app.core.clients.redis import get_redis
from app.core.logger import logger
from app.repositories.dto.judge0 import Judge0SubmissionDTO
from app.repositories.judge0 import Judge0Repository
from app.schema.evaluation import SubmissionPendingContext
from worker.redis_helper import (
    get_submission_context,
    list_pending,
    remove_from_pending_set,
)

POLLER_LOCK_KEY = "lock:eval:poller"
POLLER_LOCK_TIMEOUT = 30
# Renew the lock once this much of its TTL has elapsed, so a tick that runs
# longer than POLLER_LOCK_TIMEOUT (e.g. a slow Judge0 batch fetch across many
# chunks) doesn't let the lock expire mid-run and let a second tick start
# concurrently.
POLLER_LOCK_RENEW_INTERVAL = 10


def _is_terminal(dto: Judge0SubmissionDTO) -> bool:
    """Return True if a Judge0 result is in a terminal (completed) state."""
    try:
        return dto.is_completed
    except Exception:
        # Missing/unknown status -> treat as not-yet-terminal; the deadline path
        # will eventually force-persist it.
        return False


def _dispatch_persist(submission_id: str, timed_out: bool) -> None:
    """Enqueue the PERSIST stage for a submission on the persist queue."""
    celery_app.send_task(
        "worker.evaluation.persist_evaluation",
        args=[submission_id, timed_out],
        queue="persist",
    )


async def _poll_once() -> None:
    """Run a single poll pass over all pending submissions.

    Acquires the poller lock (non-blocking), collects every pending submission's
    tokens in batched Judge0 calls, and dispatches PERSIST for those that are
    complete or past their deadline. Submissions whose context has vanished are
    pruned from the schedule.
    """
    redis_client = get_redis()
    lock = redis_client.lock(POLLER_LOCK_KEY, timeout=POLLER_LOCK_TIMEOUT)
    acquired = await lock.acquire(blocking=False)
    if not acquired:
        logger.debug("Poller already running elsewhere; skipping this tick.")
        return

    last_renew = time.time()

    async def _renew_lock_if_needed() -> None:
        """Extend the lock's TTL if it's been a while since the last renewal.

        Best-effort: if the lock already expired under extreme load, the next
        tick's non-blocking acquire is the real safety net, so a failed renewal
        here just logs and lets this tick continue.
        """
        nonlocal last_renew
        now = time.time()
        if now - last_renew < POLLER_LOCK_RENEW_INTERVAL:
            return
        try:
            await lock.extend(POLLER_LOCK_TIMEOUT, replace_ttl=True)
            last_renew = now
        except Exception:
            logger.warning("Failed to renew poller lock; continuing this tick.")

    try:
        pending = await list_pending()

        # Gather contexts and the union of all tokens for a batched fetch.
        contexts: dict[str, tuple[SubmissionPendingContext, float]] = {}
        all_tokens: list[str] = []
        for submission_id, deadline in pending:
            ctx = await get_submission_context(submission_id)
            if ctx is None:
                # Orphaned schedule entry — context expired/cleared. Prune it.
                await remove_from_pending_set(submission_id)
                continue
            contexts[submission_id] = (ctx, deadline)
            all_tokens.extend(entry.token for entry in ctx.tokens if entry.token)

        await _renew_lock_if_needed()

        repo = Judge0Repository()
        results = await repo.get_batch_results(all_tokens) if all_tokens else {}

        await _renew_lock_if_needed()

        now = time.time()
        dispatched = 0
        for submission_id, (ctx, deadline) in contexts.items():
            await _renew_lock_if_needed()
            tokens = [entry.token for entry in ctx.tokens if entry.token]
            all_done = bool(tokens) and all(
                token in results and _is_terminal(results[token]) for token in tokens
            )

            timed_out = False
            if all_done:
                pass
            elif now > deadline:
                logger.warning(
                    f"Submission {submission_id} exceeded evaluation deadline; "
                    f"force-persisting as timed out."
                )
                timed_out = True
            else:
                continue

            # Dispatch before dropping the submission from the schedule: if the
            # broker call itself fails (connection blip), leaving it pending
            # lets the next poll tick retry instead of stranding it forever.
            try:
                _dispatch_persist(submission_id, timed_out=timed_out)
            except Exception:
                logger.error(
                    f"Failed to dispatch PERSIST for submission {submission_id}; "
                    f"will retry next poll tick.",
                    exc_info=True,
                )
                continue

            await remove_from_pending_set(submission_id)
            dispatched += 1

        if dispatched:
            logger.info(
                f"Poller dispatched PERSIST for {dispatched}/{len(contexts)} "
                f"pending submission(s)."
            )
    finally:
        try:
            await lock.release()
        except Exception:
            # Lock may have expired under heavy load; safe to ignore.
            pass


@celery_app.task
def poll_pending_evaluations() -> None:
    """Celery Beat entrypoint: run one poll pass over pending evaluations."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(_poll_once())
