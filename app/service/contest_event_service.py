from uuid import UUID

from pydantic import BaseModel

from app.core.clients.redis import get_redis
from app.core.logger import logger
from app.utils.key_builder import get_contest_channel_key


class ContestEventService:
    """Service for handling contest real-time events via Redis."""

    async def publish_event(
        self,
        contest_id: UUID,
        team_id: UUID,
        contest_team_member_id: UUID,
        event: BaseModel,
    ) -> None:
        """Publish an event to the contest channel."""
        try:
            redis_client = get_redis()
            channel = get_contest_channel_key(
                contest_id, team_id, contest_team_member_id
            )
            await redis_client.publish(channel, event.model_dump_json())
        except Exception as e:
            logger.error(f"Failed to publish event to {contest_id}: {e}")
