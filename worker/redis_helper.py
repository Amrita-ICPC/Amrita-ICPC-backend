import json
from uuid import UUID

from app.core.clients.redis import get_redis
from app.core.logger import logger


async def is_evaluation_valid(
    contest_id: UUID,
    evaluation_id: UUID,
    submission_id: UUID,
) -> bool:
    """Check if the evaluation process is valid (exists, not superseded, and not completed)."""
    redis_client = get_redis()
    redis_key = f"contests:{contest_id}:evaluation"
    data = await redis_client.get(redis_key)
    if not data:
        logger.info(
            f"No active evaluation found in Redis for contest {contest_id}. "
            f"Skipping submission {submission_id}."
        )
        return False

    eval_data = json.loads(data)
    if eval_data.get("id") != str(evaluation_id):
        logger.info(
            f"Evaluation {evaluation_id} is superseded by {eval_data.get('id')}. "
            f"Skipping submission {submission_id}."
        )
        return False

    if eval_data.get("status") == "COMPLETED":
        logger.info(
            f"Evaluation {evaluation_id} is already completed. "
            f"Skipping submission {submission_id}."
        )
        return False

    return True


async def update_evaluation_progress(
    contest_id: UUID,
    evaluation_id: UUID,
) -> None:
    """Atomically update Redis progress for the contest evaluation."""
    redis_client = get_redis()
    key = f"contests:{contest_id}:evaluation"
    async with redis_client.lock(f"lock:{key}", timeout=5):
        data = await redis_client.get(key)
        if data:
            eval_data = json.loads(data)
            # Only update if the evaluation ID matches (not superseded)
            if eval_data.get("id") == str(evaluation_id):
                eval_data["processed_submissions"] = (
                    eval_data.get("processed_submissions", 0) + 1
                )
                if eval_data["processed_submissions"] >= eval_data.get(
                    "total_submissions", 0
                ):
                    eval_data["status"] = "COMPLETED"
                    eval_data["is_evaluated"] = True
                else:
                    eval_data["status"] = "RUNNING"
                await redis_client.set(key, json.dumps(eval_data))
