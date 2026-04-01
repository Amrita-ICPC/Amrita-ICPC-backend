from typing import Awaitable, cast

import redis.asyncio as redis

from app.core.config import config
from app.core.logger import logger

redis_client: redis.Redis | None = None


async def init_redis() -> None:
    """Initialize Redis client."""
    global redis_client

    if not config.REDIS_HOST:
        logger.warning("REDIS_HOST not set. Redis client will not be initialized.")
        return

    try:
        logger.info(f"Connecting to Redis at {config.REDIS_HOST}:{config.REDIS_PORT}")
        redis_client = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT or 6379,
            password=config.REDIS_PASSWORD,
            db=config.REDIS_DB or 0,
            encoding="utf-8",
            decode_responses=True,
        )

        # Test connection
        await cast(Awaitable[bool], redis_client.ping())
        logger.info("Redis connection established successfully.")

    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        redis_client = None
        raise e


async def close_redis() -> None:
    """Close Redis client connection."""
    global redis_client
    if redis_client is not None:
        await redis_client.close()
        logger.info("Redis connection closed.")
        redis_client = None


def get_redis() -> redis.Redis:
    """Get Redis client instance."""
    if redis_client is None:
        raise RuntimeError("Redis not initialized")
    return redis_client
