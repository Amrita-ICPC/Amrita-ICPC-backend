import json
from typing import Optional
from uuid import UUID

from app.core.clients.redis import redis_client
from app.core.logger import logger
from app.models.contest import Contest


class ContestCache:
    """Cache manager for contest operations."""

    CACHE_PREFIX = "contest"
    CACHE_TTL = 300  # 5 minutes in seconds

    @staticmethod
    def _get_cache_key(contest_id: UUID) -> str:
        """Generate cache key for a contest."""
        return f"{ContestCache.CACHE_PREFIX}:{str(contest_id)}"

    @staticmethod
    def _contest_to_dict(contest: Contest) -> dict:
        """Convert contest object to dictionary for caching."""
        return {
            "id": str(contest.id),
            "name": contest.name,
            "description": contest.description,
            "image": contest.image,
            "is_public": contest.is_public,
        }

    @staticmethod
    async def get_contest(contest_id: UUID) -> Optional[dict]:
        """
        Get contest from cache.

        Args:
            contest_id: Contest ID

        Returns:
            Contest dictionary if found in cache, None otherwise
        """
        if not redis_client:
            return None

        try:
            cache_key = ContestCache._get_cache_key(contest_id)
            cached_data = await redis_client.get(cache_key)

            if cached_data:
                logger.debug(f"Cache hit for contest {contest_id}")
                return json.loads(cached_data)

            logger.debug(f"Cache miss for contest {contest_id}")
            return None

        except Exception as e:
            logger.error(f"Error getting contest from cache: {str(e)}")
            return None

    @staticmethod
    async def set_contest(contest: Contest) -> None:
        """
        Cache a contest.

        Args:
            contest: Contest object to cache
        """
        if not redis_client:
            return

        try:
            cache_key = ContestCache._get_cache_key(contest.id)
            contest_data = ContestCache._contest_to_dict(contest)

            await redis_client.setex(
                cache_key, ContestCache.CACHE_TTL, json.dumps(contest_data)
            )
            logger.debug(f"Contest {contest.id} cached successfully")

        except Exception as e:
            logger.error(f"Error caching contest: {str(e)}")

    @staticmethod
    async def delete_contest(contest_id: UUID) -> None:
        """
        Delete contest from cache.

        Args:
            contest_id: Contest ID
        """
        if not redis_client:
            return

        try:
            cache_key = ContestCache._get_cache_key(contest_id)
            await redis_client.delete(cache_key)
            logger.debug(f"Contest {contest_id} removed from cache")

        except Exception as e:
            logger.error(f"Error deleting contest from cache: {str(e)}")

    @staticmethod
    async def update_contest(contest: Contest) -> None:
        """
        Update contest in cache (delete and set).

        Args:
            contest: Updated contest object
        """
        await ContestCache.delete_contest(contest.id)
        await ContestCache.set_contest(contest)
