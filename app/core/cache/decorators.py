# app/core/cache/decorators.py
from functools import wraps
from typing import (
    Any,
    Awaitable,
    Callable,
    Optional,
    ParamSpec,
    TypeVar,
    cast,
    get_type_hints,
)

from pydantic import TypeAdapter

from app.core.cache.serialize import deserialize, serialize
from app.core.clients import redis
from app.core.config import config
from app.core.logger import logger

P = ParamSpec("P")
R = TypeVar("R")


def get_type_adapter(func: Callable[..., Any]) -> Optional[TypeAdapter[Any]]:
    """
    Helper to create a Pydantic TypeAdapter from function return annotation.
    Returns None if no return annotation or return is None.
    """
    try:
        # Resolve postponed annotations and forward refs.
        hints = get_type_hints(func, globalns=getattr(func, "__globals__", {}))
        return_type = hints.get("return")
    except Exception:
        return_type = func.__annotations__.get("return")

    if return_type and return_type is not type(None):
        try:
            adapter = TypeAdapter(return_type)
            try:
                # Ensure internal schemas are built for complex / forward-ref types.
                adapter.rebuild()
            except Exception:
                pass
            return adapter
        except Exception:
            # Fallback if TypeAdapter cannot be created (e.g. some complex types)
            return None
    return None


def cache_get(
    *,
    key_builder: Callable[P, str],
    ttl: int = 300,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator to cache the result of a function.
    Automatically handles serialization/deserialization based on return type hints.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        adapter = get_type_adapter(func)

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
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
                            try:
                                return cast(R, adapter.validate_json(cached))
                            except Exception as e:
                                logger.error(
                                    f"Error deserializing cache for key {key} via TypeAdapter: {e}"
                                )
                        cached_text = (
                            cached.decode("utf-8")
                            if isinstance(cached, (bytes, bytearray))
                            else cached
                        )
                        return cast(R, deserialize(cached_text))
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
                        try:
                            serialized_data: bytes = adapter.dump_json(result)
                        except Exception as e:
                            logger.error(
                                f"TypeAdapter dump_json failed for key {key}: {e}"
                            )
                            serialized_data = serialize(result).encode("utf-8")
                    else:
                        serialized_data = serialize(result).encode("utf-8")

                    await redis.redis_client.set(key, serialized_data, ex=ttl)
                except Exception as e:
                    logger.error(f"Redis set failed for key {key}: {e}")
            return result

        return wrapper

    return decorator


def cache_delete(
    *,
    key_builder: Callable[P, str | list[str]],
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator to delete cache entries after function execution.
    Supports single keys, list of keys, and wildcard patterns (e.g., "users:*").
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
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
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator to update a cache entry after function execution.
    Automatically handles serialization based on return type hints.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        adapter = get_type_adapter(func)

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            result = await func(*args, **kwargs)

            if config.CACHE_ENABLED and redis.redis_client:
                if from_result:
                    key = key_builder(result)
                else:
                    key = key_builder(*args, **kwargs)

                try:
                    if adapter:
                        try:
                            serialized_data: bytes = adapter.dump_json(result)
                        except Exception as e:
                            logger.error(
                                f"TypeAdapter dump_json failed for key {key}: {e}"
                            )
                            serialized_data = serialize(result).encode("utf-8")
                    else:
                        serialized_data = serialize(result).encode("utf-8")

                    await redis.redis_client.set(key, serialized_data, ex=ttl)
                    logger.info(f"Cache updated for key: {key}")
                except Exception as e:
                    logger.error(f"Redis set failed for key {key}: {e}")
            else:
                logger.debug("Cache disabled or redis unavailable, skipping update")
            return result

        return wrapper

    return decorator
