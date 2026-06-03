from typing import AsyncGenerator
from uuid import UUID

from redis.asyncio.client import Redis

from app.core.logger import logger
from app.schema.contest import ContestEvent
from app.utils.key_builder import get_contest_channel_key


class ContestEventPublisher:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def publish(
        self,
        contest_id: UUID,
        event: ContestEvent,
    ) -> None:
        try:
            count = await self.redis.publish(
                get_contest_channel_key(contest_id),
                event.model_dump_json(),
            )

            logger.info(f"Event published with:{count}")

        except Exception:
            logger.error(
                "Error publishing contest event",
                extra={
                    "contest_id": contest_id,
                    "event": event,
                },
            )

    async def subscribe(
        self, contest_id: UUID, user_id: UUID | None = None
    ) -> AsyncGenerator[str, None]:
        """Subscribe to contest events and yield them as SSE data packets."""
        pubsub = self.redis.pubsub()
        channel = get_contest_channel_key(contest_id)
        await pubsub.subscribe(channel)
        logger.info(f"Subscribed user={user_id} contest={contest_id} channel={channel}")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield f"data: {message['data']}\n\n"
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            logger.info(f"Unsubscribed user={user_id} contest={contest_id}")
