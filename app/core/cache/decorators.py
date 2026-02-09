# app/core/cache/decorators.py
from functools import wraps
from typing import Callable, Optional

from pydantic import TypeAdapter

from app.core.cache.serialize import deserialize, serialize
from app.core.clients import redis
from app.core.config import config
from app.core.logger import logger


def get_type_adapter(func: Callable) -> Optional[TypeAdapter]:
    """
    Helper to create a Pydantic TypeAdapter from function return annotation.
    Returns None if no return annotation or return is None.
    """
    return_type = func.__annotations__.get("return")
    if return_type and return_type is not type(None):
        try:
            return TypeAdapter(return_type)
        except Exception:
            # Fallback if TypeAdapter cannot be created (e.g. some complex types)
            return None
    return None


def cache_get(
    *,
    key_builder: Callable[..., str],
    ttl: int = 300,
):
    """
    Decorator to cache the result of a function.
    Automatically handles serialization/deserialization based on return type hints.
    """

    def decorator(func):
        adapter = get_type_adapter(func)

        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not config.CACHE_ENABLED:
                logger.debug("Cache disabled, bypassing cache get")
                return await func(*args, **kwargs)

            key = key_builder(*args, **kwargs)

            if not redis.redis_client:
                logger.warning("Redis client not initialized, skipping cache get")
                return await func(*args, **kwargs)

            try:
                cached = await redis.redis_client.get(key)
                if cached is not None:
                    logger.info(f"Cache hit for key: {key}")
                    try:
                        if adapter:
                            return adapter.validate_json(cached)
                        return deserialize(cached)
                    except Exception as e:
                        logger.error(f"Error deserializing cache for key {key}: {e}")
            except Exception as e:
                logger.error(f"Redis get failed for key {key}: {e}")

            logger.info(f"Cache miss for key: {key}")
            result = await func(*args, **kwargs)

            if redis.redis_client:
                try:
                    if adapter:
                        # dump_json returns bytes
                        serialized_data = adapter.dump_json(result)
                    else:
                        serialized_data = serialize(result)

                    await redis.redis_client.set(key, serialized_data, ex=ttl)
                except Exception as e:
                    logger.error(f"Redis set failed for key {key}: {e}")
            return result

        return wrapper

    return decorator


def cache_delete(
    *,
    key_builder: Callable[..., str | list[str]],
):
    """
    Decorator to delete cache entries after function execution.
    Supports single keys, list of keys, and wildcard patterns (e.g., "users:*").
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            if config.CACHE_ENABLED and redis.redis_client:
                keys_or_key = key_builder(*args, **kwargs)
                keys = [keys_or_key] if isinstance(keys_or_key, str) else keys_or_key

                for key_pattern in keys:
                    try:
                        if "*" in key_pattern:
                            # Use scan_iter for wildcard matching
                            cursor = 0
                            while True:
                                cursor, matches = await redis.redis_client.scan(
                                    cursor, match=key_pattern, count=100
                                )
                                if matches:
                                    await redis.redis_client.delete(*matches)
                                    logger.info(
                                        f"Cache invalidated for pattern: {key_pattern} ({len(matches)} keys)"
                                    )
                                if cursor == 0:
                                    break
                        else:
                            await redis.redis_client.delete(key_pattern)
                            logger.info(f"Cache invalidated for key: {key_pattern}")

                    except Exception as e:
                        logger.error(
                            f"Redis delete failed for key/pattern {key_pattern}: {e}"
                        )
            else:
                logger.debug(
                    "Cache disabled or redis unavailable, skipping invalidation"
                )
            return result

        return wrapper

    return decorator


def cache_set(
    *,
    key_builder: Callable[..., str],
    ttl: int = 300,
    from_result: bool = False,
):
    """
    Decorator to update a cache entry after function execution.
    Automatically handles serialization based on return type hints.
    """

    def decorator(func):
        adapter = get_type_adapter(func)

        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            if config.CACHE_ENABLED and redis.redis_client:
                if from_result:
                    key = key_builder(result)
                else:
                    key = key_builder(*args, **kwargs)

                try:
                    if adapter:
                        serialized_data = adapter.dump_json(result)
                    else:
                        serialized_data = serialize(result)

                    await redis.redis_client.set(key, serialized_data, ex=ttl)
                    logger.info(f"Cache updated for key: {key}")
                except Exception as e:
                    logger.error(f"Redis set failed for key {key}: {e}")
            else:
                logger.debug("Cache disabled or redis unavailable, skipping update")
            return result

        return wrapper

    return decorator
