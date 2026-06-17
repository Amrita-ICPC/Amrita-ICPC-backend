from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import LockError

from app.core.cache.decorators import cache_get
from app.core.clients import redis
from app.core.config import config


# Define a dummy function to decorate
async def dummy_function(x: int) -> int:
    return x * 2


@pytest.mark.asyncio
async def test_cache_get_lock_success():
    """Test successful lock acquisition, function execution, and cache set on miss."""
    mock_lock = MagicMock()
    mock_lock.__aenter__ = AsyncMock(return_value=mock_lock)
    mock_lock.__aexit__ = AsyncMock(return_value=None)

    mock_redis = MagicMock()
    mock_redis.lock.return_value = mock_lock
    # Cache miss on both checks (get returns None)
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()

    with (
        patch.object(config, "CACHE_ENABLED", True),
        patch.object(redis, "redis_client", mock_redis),
    ):
        decorated = cache_get(
            key_builder=lambda x: f"test:{x}", use_lock=True, lock_timeout=5
        )(dummy_function)
        result = await decorated(10)

        assert result == 20
        assert mock_redis.get.call_count == 2
        mock_redis.get.assert_any_call("test:10")
        mock_redis.lock.assert_called_once_with(
            name="lock:test:10",
            timeout=5,
            sleep=0.1,
            blocking=True,
            blocking_timeout=5.0,
        )
        mock_lock.__aenter__.assert_awaited_once()
        mock_lock.__aexit__.assert_awaited_once()
        mock_redis.set.assert_called_once()


@pytest.mark.asyncio
async def test_cache_get_lock_custom_parameters():
    """Test cache locking with custom values for blocking, sleep, and blocking_timeout."""
    mock_lock = MagicMock()
    mock_lock.__aenter__ = AsyncMock(return_value=mock_lock)
    mock_lock.__aexit__ = AsyncMock(return_value=None)

    mock_redis = MagicMock()
    mock_redis.lock.return_value = mock_lock
    # Cache miss
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()

    with (
        patch.object(config, "CACHE_ENABLED", True),
        patch.object(redis, "redis_client", mock_redis),
    ):
        decorated = cache_get(
            key_builder=lambda x: f"test:{x}",
            use_lock=True,
            lock_timeout=8.0,
            lock_blocking=False,
            lock_blocking_timeout=2.5,
            lock_sleep=0.05,
        )(dummy_function)
        result = await decorated(10)

        assert result == 20
        assert mock_redis.get.call_count == 2
        mock_redis.lock.assert_called_once_with(
            name="lock:test:10",
            timeout=8.0,
            sleep=0.05,
            blocking=False,
            blocking_timeout=2.5,
        )
        mock_lock.__aenter__.assert_awaited_once()
        mock_lock.__aexit__.assert_awaited_once()
        mock_redis.set.assert_called_once()


@pytest.mark.asyncio
async def test_cache_get_lock_hit_no_lock():
    """Test that a cache hit on the first check returns cached value immediately without locking."""
    mock_redis = MagicMock()
    # Cache hit (get returns serialized 40)
    mock_redis.get = AsyncMock(return_value=b"40")

    # We will spy on dummy_function execution by using a mock wrapper
    spy_func = AsyncMock(return_value=20)

    with (
        patch.object(config, "CACHE_ENABLED", True),
        patch.object(redis, "redis_client", mock_redis),
    ):
        decorated = cache_get(key_builder=lambda x: f"test:{x}", use_lock=True)(
            spy_func
        )
        result = await decorated(10)

        assert result == 40
        spy_func.assert_not_called()
        mock_redis.lock.assert_not_called()
        mock_redis.get.assert_called_once_with("test:10")


@pytest.mark.asyncio
async def test_cache_get_double_checked_lock_hit():
    """
    Test that if there is a miss on the first check, but the lock is acquired,
    and a second check finds the value cached (populated by another process),
    it returns the cached value and does NOT execute the target function.
    """
    mock_lock = MagicMock()
    mock_lock.__aenter__ = AsyncMock(return_value=mock_lock)
    mock_lock.__aexit__ = AsyncMock(return_value=None)

    mock_redis = MagicMock()
    mock_redis.lock.return_value = mock_lock
    # First get returns None (miss), second get returns serialized 40 (hit)
    mock_redis.get = AsyncMock(side_effect=[None, b"40"])

    spy_func = AsyncMock(return_value=20)

    with (
        patch.object(config, "CACHE_ENABLED", True),
        patch.object(redis, "redis_client", mock_redis),
    ):
        decorated = cache_get(key_builder=lambda x: f"test:{x}", use_lock=True)(
            spy_func
        )
        result = await decorated(10)

        assert result == 40
        spy_func.assert_not_called()
        mock_redis.lock.assert_called_once()
        assert mock_redis.get.call_count == 2
        mock_lock.__aenter__.assert_awaited_once()
        mock_lock.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_get_lock_bypass_when_disabled():
    """Test lock decorator bypasses locking when cache is disabled."""
    mock_redis = MagicMock()

    with (
        patch.object(config, "CACHE_ENABLED", False),
        patch.object(redis, "redis_client", mock_redis),
    ):
        decorated = cache_get(key_builder=lambda x: f"test:{x}", use_lock=True)(
            dummy_function
        )
        result = await decorated(10)

        assert result == 20
        mock_redis.lock.assert_not_called()


@pytest.mark.asyncio
async def test_cache_get_lock_failure_fallback():
    """Test that lock failure falls back to execution instead of propagating LockError."""
    mock_lock = MagicMock()
    mock_lock.__aenter__ = AsyncMock(side_effect=LockError("Lock acquisition failed"))
    mock_lock.__aexit__ = MagicMock()

    mock_redis = MagicMock()
    mock_redis.lock.return_value = mock_lock
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()

    with (
        patch.object(config, "CACHE_ENABLED", True),
        patch.object(redis, "redis_client", mock_redis),
    ):
        decorated = cache_get(key_builder=lambda x: f"test:{x}", use_lock=True)(
            dummy_function
        )
        result = await decorated(10)

        assert result == 20
        mock_redis.lock.assert_called_once()
        mock_lock.__aenter__.assert_awaited_once()
        # Initial get only
        mock_redis.get.assert_called_once_with("test:10")
