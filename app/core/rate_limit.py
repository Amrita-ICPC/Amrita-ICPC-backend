"""Per-user, Redis-backed API rate limiting for Judge0-fronting endpoints.

Uses fastapi-limiter's ``RateLimiter`` dependency, backed by pyrate_limiter's
Redis bucket implementation (the ``fastapi-limiter`` version pinned in this
project is the pyrate_limiter-based rewrite, not the older
``FastAPILimiter.init(redis)`` package -- there is no ``FastAPILimiter`` class
to initialize here).

pyrate_limiter's own ``SingleBucketFactory`` (used automatically when a
``Limiter`` is built from a plain rate list or a single bucket) always
returns the *same* bucket regardless of the caller, which would make every
student share one global counter. ``_LazyRedisBucketFactory`` below instead
keeps one Redis-backed bucket per distinct rate-limit key, so each user is
limited independently while every app instance/worker enforces the same
counters (since the state lives in Redis, not in a worker's memory).
"""

import time
from typing import Dict

from fastapi import Depends, params
from fastapi_limiter.depends import RateLimiter
from pyrate_limiter import (
    AbstractBucket,
    BucketFactory,
    Limiter,
    Rate,
    RateItem,
    RedisBucket,
)
from starlette.requests import Request

from app.core.clients import redis as redis_client_module
from app.core.logger import logger


async def init_rate_limiter() -> None:
    """Confirm the rate limiter's Redis dependency is ready.

    Call from the app lifespan right after ``init_redis()``. Unlike the
    classic ``FastAPILimiter.init(redis)`` API, ``rate_limit()`` dependencies
    below don't need a value handed to them here -- each one looks up
    ``app.core.clients.redis.redis_client`` lazily on first request (see
    ``_LazyRedisBucketFactory.get``), since route ``dependencies=[...]`` are
    built at import time, before the lifespan has connected to Redis. This
    function exists to fail fast at startup instead of silently degrading
    into 500s on a route's first request if Redis never came up.

    Raises:
        RuntimeError: If Redis was not initialized before this is called.
    """
    if redis_client_module.redis_client is None:
        raise RuntimeError(
            "Rate limiter requires Redis: init_redis() must be called and "
            "succeed before init_rate_limiter()."
        )
    logger.info("Rate limiter ready (Redis-backed, per-user request buckets)")


async def _user_identifier(request: Request) -> str:
    """Key rate limits by the authenticated Keycloak user, not by IP.

    Falls back to the default IP-based identity only if a request somehow
    reaches this dependency without going through the Keycloak auth
    middleware. IP-based keying alone would be wrong here: many students on
    the same campus network/NAT would share one bucket and throttle each
    other.
    """
    user = getattr(request, "user", None)
    if user is not None:
        sub = user.get("sub") if isinstance(user, dict) else getattr(user, "sub", None)
        if sub:
            return str(sub)

    from fastapi_limiter.identifier import default_identifier

    return await default_identifier(request)


class _LazyRedisBucketFactory(BucketFactory):
    """One Redis-backed bucket per rate-limit key, created on first use.

    The Redis client is looked up lazily (via the shared
    ``app.core.clients.redis`` module) rather than captured at import time,
    because route decorators run at import time -- before ``init_redis()``
    has connected in the app lifespan. By the time an actual HTTP request
    reaches this factory's ``get()``, redis has already been initialized.
    """

    def __init__(self, rates: list[Rate], namespace: str):
        self.rates = rates
        self.namespace = namespace
        self._buckets: Dict[str, AbstractBucket] = {}

    def wrap_item(self, name: str, weight: int = 1) -> RateItem:
        return RateItem(name, int(time.time() * 1000), weight=weight)

    async def get(self, item: RateItem) -> AbstractBucket:
        bucket = self._buckets.get(item.name)
        if bucket is not None:
            return bucket

        redis = redis_client_module.redis_client
        if redis is None:
            raise RuntimeError(
                "Rate limiter used before Redis was initialized: "
                "init_redis() must run in the app lifespan before requests are served."
            )

        bucket = await RedisBucket.init(
            self.rates, redis, f"rate_limit:{self.namespace}:{item.name}"
        )
        self._buckets[item.name] = bucket
        return bucket


def rate_limit(times: int, seconds: int, *, namespace: str) -> params.Depends:
    """Build a per-user Redis-backed rate limit dependency for a route.

    Args:
        times: Max requests allowed within the window.
        seconds: Window size in seconds.
        namespace: Unique label for this limit (keeps its Redis keys/bucket
            cache separate from other routes using their own `rate_limit()`).

    Returns:
        A FastAPI dependency to add to a route's ``dependencies=[...]``.
    """
    rates = [Rate(times, seconds * 1000)]
    limiter = Limiter(_LazyRedisBucketFactory(rates, namespace=namespace))
    return Depends(RateLimiter(limiter=limiter, identifier=_user_identifier))
