"""Redis coordination layer for the staged evaluation pipeline.

This module is the single owner of every Redis key used by evaluation. It holds
all *transient* lifecycle state (which submissions are awaiting Judge0 results,
their token maps, in-flight/backpressure counters and per-contest progress). None
of this is persisted to the database — the database only ever records terminal
verdicts.

Every value stored here is a typed Pydantic model (see ``app.schema.evaluation``),
serialized with ``model_dump_json`` / parsed with ``model_validate_json``. Callers
never read or write raw dicts for these keys — that keeps the Redis contract
explicit and type-checked instead of being implicit string-keyed JSON.

Key layout
----------
- ``eval:pending``                       sorted set; member=submission_id,
                                          score=deadline epoch. The poller scans
                                          this to know what to collect.
- ``eval:sub:{submission_id}``           JSON-encoded ``SubmissionPendingContext``;
                                          the full collect/persist context for one
                                          submission (token map, contest context,
                                          limits, deadline).
- ``eval:inflight``                      integer; submissions currently awaiting
                                          Judge0 results (global backpressure gate).
- ``contests:{cid}:evaluation``          JSON-encoded ``EvaluationRecord``;
                                          immutable bulk-evaluation metadata.
- ``contests:{cid}:eval:{eid}:processed``integer; atomically incremented as
                                          submissions finish (no lock).
- ``contests:{cid}:eval:{eid}:active``   integer; per-contest in-flight gate for
                                          bulk evaluation fairness.
- ``contests:{cid}:eval:{eid}:counted``  set of submission_ids already counted
                                          toward progress (exactly-once guard).
"""

from uuid import UUID

from app.core.clients.redis import get_redis
from app.core.logger import logger
from app.schema.evaluation import EvaluationRecord, SubmissionPendingContext

# Default TTL for per-submission context so orphaned keys self-expire.
SUB_CONTEXT_TTL_SECONDS = 3600
# TTL for per-contest counters after an evaluation finishes.
CONTEST_COUNTER_TTL_SECONDS = 86400


# --------------------------------------------------------------------------- #
# Key builders                                                                #
# --------------------------------------------------------------------------- #
def pending_key() -> str:
    """Return the sorted-set key tracking submissions awaiting collection."""
    return "eval:pending"


def sub_key(submission_id: UUID | str) -> str:
    """Return the context key for a single in-flight submission."""
    return f"eval:sub:{submission_id}"


def inflight_key() -> str:
    """Return the global in-flight backpressure counter key."""
    return "eval:inflight"


def contest_eval_key(contest_id: UUID | str) -> str:
    """Return the bulk-evaluation metadata key for a contest."""
    return f"contests:{contest_id}:evaluation"


def contest_processed_key(contest_id: UUID | str, evaluation_id: UUID | str) -> str:
    """Return the atomic processed-count key for a bulk evaluation."""
    return f"contests:{contest_id}:eval:{evaluation_id}:processed"


def contest_active_key(contest_id: UUID | str, evaluation_id: UUID | str) -> str:
    """Return the per-contest active (in-flight) gate key for a bulk evaluation."""
    return f"contests:{contest_id}:eval:{evaluation_id}:active"


def contest_counted_key(contest_id: UUID | str, evaluation_id: UUID | str) -> str:
    """Return the set key of submissions already counted toward progress.

    Used to make progress counting exactly-once per submission, even across task
    retries or worker crashes.
    """
    return f"contests:{contest_id}:eval:{evaluation_id}:counted"


# --------------------------------------------------------------------------- #
# Pending set & per-submission context                                        #
# --------------------------------------------------------------------------- #
async def register_pending(
    submission_id: UUID, context: SubmissionPendingContext, deadline: float
) -> None:
    """Register a submission as awaiting Judge0 results.

    Stores the collect/persist context and adds the submission to the pending
    sorted set scored by its deadline so the poller can both collect it and
    detect when it has timed out.

    Args:
        submission_id: The submission being tracked.
        context: Typed collect/persist context (token map, contest context,
            limits, flags).
        deadline: Absolute epoch time after which the submission is considered
            timed out and force-persisted.
    """
    redis_client = get_redis()
    await redis_client.set(
        sub_key(submission_id), context.model_dump_json(), ex=SUB_CONTEXT_TTL_SECONDS
    )
    await redis_client.zadd(pending_key(), {str(submission_id): deadline})


async def get_submission_context(
    submission_id: UUID | str,
) -> SubmissionPendingContext | None:
    """Return the stored collect/persist context for a submission, if present."""
    redis_client = get_redis()
    data = await redis_client.get(sub_key(submission_id))
    if not data:
        return None
    return SubmissionPendingContext.model_validate_json(data)


async def list_pending() -> list[tuple[str, float]]:
    """Return all pending submissions as ``(submission_id, deadline)`` tuples."""
    redis_client = get_redis()
    members = await redis_client.zrange(pending_key(), 0, -1, withscores=True)
    return [(member, score) for member, score in members]


async def remove_from_pending_set(submission_id: UUID | str) -> None:
    """Remove a submission from the pending *schedule* but keep its context.

    The poller calls this when it dispatches PERSIST so the submission is not
    polled again, while leaving the context in place for the PERSIST stage to
    consume. PERSIST then calls :func:`clear_pending` to drop the context.
    """
    redis_client = get_redis()
    await redis_client.zrem(pending_key(), str(submission_id))


async def clear_pending(submission_id: UUID | str) -> None:
    """Remove a submission from the pending set and delete its context."""
    redis_client = get_redis()
    await redis_client.zrem(pending_key(), str(submission_id))
    await redis_client.delete(sub_key(submission_id))


async def is_pending(submission_id: UUID | str) -> bool:
    """Return True if the submission is already awaiting collection."""
    redis_client = get_redis()
    return await redis_client.zscore(pending_key(), str(submission_id)) is not None


# --------------------------------------------------------------------------- #
# Backpressure gates                                                          #
# --------------------------------------------------------------------------- #
async def try_acquire_inflight(cap: int, amount: int = 1) -> bool:
    """Atomically reserve global in-flight capacity.

    Args:
        cap: Maximum allowed in-flight submissions.
        amount: Units to reserve (usually 1).

    Returns:
        True if capacity was reserved; False if the cap would be exceeded (in
        which case nothing is reserved).
    """
    redis_client = get_redis()
    new_val = await redis_client.incrby(inflight_key(), amount)
    if new_val > cap:
        await redis_client.decrby(inflight_key(), amount)
        return False
    return True


async def release_inflight(amount: int = 1) -> None:
    """Release previously reserved global in-flight capacity (never below zero)."""
    redis_client = get_redis()
    new_val = await redis_client.decrby(inflight_key(), amount)
    if new_val < 0:
        # Clamp defensively if releases ever outpace reservations.
        await redis_client.set(inflight_key(), 0)


async def try_acquire_contest_slot(
    contest_id: UUID | str, evaluation_id: UUID | str, cap: int, amount: int = 1
) -> bool:
    """Atomically reserve a per-contest active slot for bulk evaluation.

    Args:
        contest_id: Contest owning the bulk evaluation.
        evaluation_id: The bulk evaluation run.
        cap: Maximum concurrent in-flight submissions for this contest.
        amount: Units to reserve (usually 1).

    Returns:
        True if a slot was reserved; False if the cap would be exceeded.
    """
    redis_client = get_redis()
    key = contest_active_key(contest_id, evaluation_id)
    new_val = await redis_client.incrby(key, amount)
    if new_val > cap:
        await redis_client.decrby(key, amount)
        return False
    await redis_client.expire(key, CONTEST_COUNTER_TTL_SECONDS)
    return True


async def release_contest_slot(
    contest_id: UUID | str, evaluation_id: UUID | str, amount: int = 1
) -> None:
    """Release a previously reserved per-contest active slot (never below zero)."""
    redis_client = get_redis()
    key = contest_active_key(contest_id, evaluation_id)
    new_val = await redis_client.decrby(key, amount)
    if new_val < 0:
        await redis_client.set(key, 0)


# --------------------------------------------------------------------------- #
# Bulk-evaluation metadata & progress                                         #
# --------------------------------------------------------------------------- #
async def create_evaluation(record: EvaluationRecord) -> None:
    """Persist immutable bulk-evaluation metadata and reset its progress counter.

    Args:
        record: The new evaluation run's immutable metadata.
    """
    redis_client = get_redis()
    await redis_client.set(
        contest_eval_key(record.contest_id), record.model_dump_json()
    )
    # Reset processed/active counters and the counted-set for the new run.
    await redis_client.set(
        contest_processed_key(record.contest_id, record.id),
        0,
        ex=CONTEST_COUNTER_TTL_SECONDS,
    )
    await redis_client.set(
        contest_active_key(record.contest_id, record.id),
        0,
        ex=CONTEST_COUNTER_TTL_SECONDS,
    )
    await redis_client.delete(contest_counted_key(record.contest_id, record.id))


async def get_evaluation_record(contest_id: UUID | str) -> EvaluationRecord | None:
    """Return the current bulk-evaluation metadata for a contest, if any."""
    redis_client = get_redis()
    data = await redis_client.get(contest_eval_key(contest_id))
    if not data:
        return None
    return EvaluationRecord.model_validate_json(data)


async def get_processed_count(contest_id: UUID | str, evaluation_id: UUID | str) -> int:
    """Return the number of submissions processed so far for an evaluation."""
    redis_client = get_redis()
    val = await redis_client.get(contest_processed_key(contest_id, evaluation_id))
    return int(val) if val is not None else 0


def derive_status(processed: int, total: int) -> str:
    """Derive a coarse evaluation status from progress counters.

    Args:
        processed: Submissions processed so far.
        total: Total submissions in the run.

    Returns:
        ``"COMPLETED"`` once all are processed, ``"RUNNING"`` while in progress,
        otherwise ``"PENDING"``.
    """
    if total <= 0 or processed >= total:
        return "COMPLETED"
    if processed > 0:
        return "RUNNING"
    return "PENDING"


async def is_evaluation_valid(
    contest_id: UUID,
    evaluation_id: UUID,
    submission_id: UUID,
) -> bool:
    """Check that a bulk evaluation is still the active, uncompleted run.

    Used to short-circuit work for submissions belonging to an evaluation that
    has been superseded by a newer run or already completed.

    Args:
        contest_id: Contest owning the evaluation.
        evaluation_id: The evaluation this submission belongs to.
        submission_id: Submission being processed (for logging only).

    Returns:
        True if the evaluation exists, matches ``evaluation_id`` and is not yet
        complete; False otherwise.
    """
    record = await get_evaluation_record(contest_id)
    if not record:
        logger.info(
            f"No active evaluation in Redis for contest {contest_id}; "
            f"skipping submission {submission_id}."
        )
        return False

    if record.id != evaluation_id:
        logger.info(
            f"Evaluation {evaluation_id} superseded by {record.id}; "
            f"skipping submission {submission_id}."
        )
        return False

    processed = await get_processed_count(contest_id, evaluation_id)
    if derive_status(processed, record.total_submissions) == "COMPLETED":
        logger.info(
            f"Evaluation {evaluation_id} already completed; "
            f"skipping submission {submission_id}."
        )
        return False

    return True


async def update_evaluation_progress(
    contest_id: UUID,
    evaluation_id: UUID,
    submission_id: UUID,
) -> None:
    """Record that one submission of a bulk evaluation has finished — exactly once.

    A submission is added to a per-evaluation "counted" set first; the processed
    counter is incremented only when the submission was newly added. This makes
    progress idempotent across task retries, duplicate poller dispatches and
    worker crashes, while remaining lock-free (``SADD``/``INCR`` are atomic).

    Args:
        contest_id: Contest owning the evaluation.
        evaluation_id: The evaluation being advanced.
        submission_id: The submission that finished (the idempotency key).
    """
    redis_client = get_redis()
    record = await get_evaluation_record(contest_id)
    # Only count progress for the active (non-superseded) run.
    if not record or record.id != evaluation_id:
        return
    counted_key = contest_counted_key(contest_id, evaluation_id)
    added = await redis_client.sadd(counted_key, str(submission_id))
    await redis_client.expire(counted_key, CONTEST_COUNTER_TTL_SECONDS)
    if added:
        await redis_client.incr(contest_processed_key(contest_id, evaluation_id))
