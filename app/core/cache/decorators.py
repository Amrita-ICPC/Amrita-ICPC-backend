# app/core/cache/decorators.py
import contextvars
from contextlib import asynccontextmanager
from functools import wraps
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Optional,
    ParamSpec,
    TypeVar,
    cast,
    get_type_hints,
)

from pydantic import TypeAdapter
from redis.exceptions import LockError

from app.core.cache.serialize import deserialize, serialize
from app.core.clients import redis
from app.core.config import config
from app.core.logger import logger

P = ParamSpec("P")
R = TypeVar("R")

# Keys queued by @cache_delete while inside a defer_cache_invalidation() scope,
# instead of being deleted immediately. None means "no active scope" - i.e.
# delete immediately, the historical behavior (used by workers/scripts that
# manage their own commit timing).
_pending_invalidations: contextvars.ContextVar[Optional[list[str]]] = (
    contextvars.ContextVar("_pending_invalidations", default=None)
)


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
        annotations = getattr(func, "__annotations__", None)
        return_type = (
            annotations.get("return") if isinstance(annotations, dict) else None
        )

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
    use_lock: bool = False,
    lock_timeout: float = 30.0,
    lock_blocking: bool = True,
    lock_blocking_timeout: Optional[float] = 5.0,
    lock_sleep: float = 0.1,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator to cache the result of a function.
    Automatically handles serialization/deserialization based on return type hints.
    Supports distributed cache locking to prevent cache stampedes.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        adapter = get_type_adapter(func)

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not config.CACHE_ENABLED or not redis.redis_client:
                logger.debug("Cache disabled or redis unavailable, bypassing cache get")
                return await func(*args, **kwargs)

            key = key_builder(*args, **kwargs)

            async def get_from_cache() -> Optional[R]:
                try:
                    cached = await redis.redis_client.get(key)
                    if cached is not None:
                        logger.info(f"Cache hit for key: {key}")
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
                    logger.error(f"Redis get failed for key {key}: {e}")
                return None

            async def set_in_cache(value: R) -> None:
                try:
                    if adapter:
                        try:
                            serialized_data = adapter.dump_json(value)
                        except Exception as e:
                            logger.error(
                                f"TypeAdapter dump_json failed for key {key}: {e}"
                            )
                            serialized_data = serialize(value).encode("utf-8")
                    else:
                        serialized_data = serialize(value).encode("utf-8")

                    await redis.redis_client.set(key, serialized_data, ex=ttl)
                except Exception as e:
                    logger.error(f"Redis set failed for key {key}: {e}")

            cached_val = await get_from_cache()
            if cached_val is not None:
                return cached_val

            if use_lock:
                lock_key = f"lock:{key}"
                lock = redis.redis_client.lock(
                    name=lock_key,
                    timeout=lock_timeout,
                    sleep=lock_sleep,
                    blocking=lock_blocking,
                    blocking_timeout=lock_blocking_timeout,
                )
                try:
                    async with lock:
                        cached_val = await get_from_cache()
                        if cached_val is not None:
                            return cached_val

                        logger.info(f"Cache miss for key: {key}")
                        result = await func(*args, **kwargs)
                        await set_in_cache(result)
                        return result
                except LockError as e:
                    logger.error(f"Redis lock failed for key {lock_key}: {e}")
                    logger.info(f"Cache miss for key (lock fallback): {key}")
                    result = await func(*args, **kwargs)
                    await set_in_cache(result)
                    return result
            else:
                logger.info(f"Cache miss for key: {key}")
                result = await func(*args, **kwargs)
                await set_in_cache(result)
                return result

        return wrapper

    return decorator


async def delete_cache_keys(keys_or_pattern: str | list[str]) -> None:
    """
    Delete cache keys matching a specific key, list of keys, or wildcard pattern.
    """
    if not config.CACHE_ENABLED or not redis.redis_client:
        return

    keys = [keys_or_pattern] if isinstance(keys_or_pattern, str) else keys_or_pattern

    for key_pattern in keys:
        try:
            if "*" in key_pattern:
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
            logger.error(f"Redis delete failed for key/pattern {key_pattern}: {e}")


@asynccontextmanager
async def defer_cache_invalidation() -> AsyncIterator[None]:
    """
    Collect cache_delete invocations made within this scope and flush them
    once on clean exit, instead of deleting immediately as each decorated
    service method returns.

    Why this exists: the request-scoped DB session (see get_db) commits the
    transaction *after* the endpoint/service call returns. @cache_delete used
    to delete cache keys immediately on return, i.e. before that commit ran.
    A concurrent request landing in that window would see the old row,
    repopulate the cache with pre-commit (stale) data, and that data would
    then sit there for the full TTL. Wrapping the request in this scope (see
    get_db) and flushing only after the commit succeeds closes that window.

    Nesting-safe: an inner scope reuses the outer one's pending list rather
    than shadowing it, so a nested "async with defer_cache_invalidation()"
    still flushes at the outermost exit, not the inner one.
    """
    outer_pending = _pending_invalidations.get()
    if outer_pending is not None:
        # Already inside a scope (e.g. nested get_db) - just participate in it.
        yield
        return

    token = _pending_invalidations.set([])
    try:
        yield
        pending = _pending_invalidations.get()
        if pending:
            await delete_cache_keys(pending)
    finally:
        _pending_invalidations.reset(token)


async def _invalidate_or_defer(keys_or_pattern: str | list[str]) -> None:
    """Queue for post-commit flush if inside defer_cache_invalidation(),
    otherwise delete immediately (the historical, pre-deferral behavior)."""
    pending = _pending_invalidations.get()
    if pending is None:
        await delete_cache_keys(keys_or_pattern)
        return
    keys = [keys_or_pattern] if isinstance(keys_or_pattern, str) else keys_or_pattern
    pending.extend(keys)


def cache_delete(
    *,
    key_builder: Callable[P, str | list[str]],
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator to delete cache entries after function execution.
    Supports single keys, list of keys, and wildcard patterns (e.g., "users:*").

    If called from within a defer_cache_invalidation() scope (the normal case
    for HTTP requests - see get_db), the actual delete is queued and only runs
    after that scope's DB transaction commits.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            result = await func(*args, **kwargs)
            keys_or_key = key_builder(*args, **kwargs)
            await _invalidate_or_defer(keys_or_key)
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
