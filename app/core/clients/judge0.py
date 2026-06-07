"""Judge0 API client for async code execution - Enterprise-grade implementation."""

import asyncio
from enum import Enum
from typing import Optional

import httpx

from app.core.config import config
from app.core.logger import logger
from app.exceptions.judge0 import (
    Judge0NotInitializedError,
)


class Judge0StatusCode(int, Enum):
    """Judge0 submission status IDs.

    Reference: https://judge0.com/docs/status-codes
    """

    IN_QUEUE = 1
    PROCESSING = 2
    ACCEPTED = 3
    WRONG_ANSWER = 4
    TIME_LIMIT_EXCEEDED = 5
    COMPILATION_ERROR = 6
    RUNTIME_ERROR_SIGSEGV = 7
    RUNTIME_ERROR_SIGXFSZ = 8
    RUNTIME_ERROR_SIGFPE = 9
    RUNTIME_ERROR_SIGABRT = 10
    RUNTIME_ERROR_NZEC = 11
    RUNTIME_ERROR_OTHER = 12
    INTERNAL_ERROR = 13
    EXEC_FORMAT_ERROR = 14


# Global async client instance
judge0_client: Optional[httpx.AsyncClient] = None
_client_init_lock = asyncio.Lock()

# CLIENT INITIALIZATION


async def init_judge0() -> None:
    """Initialize Judge0 HTTP client with connection pooling.

    Thread-safe initialization using asyncio.Lock to prevent race conditions.
    """
    global judge0_client

    if judge0_client is not None:
        logger.debug("Judge0 client already initialized")
        return

    async with _client_init_lock:
        # Double-check after acquiring lock
        if judge0_client is not None:
            return

        if not config.JUDGE0_API_URL:
            logger.error(
                "JUDGE0_API_URL not configured. Judge0 code execution service is unavailable."
            )
            raise Judge0NotInitializedError(
                "Judge0 API URL is not configured. Code execution service is disabled."
            )

        try:
            # Build headers with optional API key
            headers: dict[str, str] = {
                "Content-Type": "application/json",
                "User-Agent": "AmritaICPC/1.0",
            }

            # Only add API key if provided (supports both authenticated and public instances)
            if config.JUDGE0_API_KEY:
                headers["X-Auth-Token"] = config.JUDGE0_API_KEY
                logger.info("Judge0 authenticated client configured (X-Auth-Token set)")
            else:
                logger.warning(
                    "JUDGE0_API_KEY not set; using unauthenticated Judge0 requests. "
                    "Public quota limits may apply."
                )

            # Create persistent async client with connection pooling
            judge0_client = httpx.AsyncClient(
                base_url=config.JUDGE0_API_URL.rstrip("/"),
                headers=headers,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                timeout=config.JUDGE0_API_TIMEOUT,
            )

            logger.info(
                "Judge0 client initialized successfully",
                extra={
                    "api_url": config.JUDGE0_API_URL,
                    "timeout": config.JUDGE0_API_TIMEOUT,
                },
            )

        except Exception as e:
            logger.error(f"Failed to initialize Judge0 client: {str(e)}")
            judge0_client = None
            raise


async def close_judge0() -> None:
    """Gracefully close Judge0 client connection."""
    global judge0_client

    if judge0_client is not None:
        try:
            await judge0_client.aclose()
            logger.info("Judge0 client closed successfully")
        except Exception as e:
            logger.error(f"Error closing Judge0 client: {e}")
        finally:
            judge0_client = None


def get_judge0_client() -> httpx.AsyncClient:
    """Get Judge0 client instance.

    Returns:
        Initialized httpx.AsyncClient

    Raises:
        Judge0NotInitializedError: If Judge0 is not configured or initialized
    """
    if judge0_client is None:
        raise Judge0NotInitializedError(
            "Judge0 client not initialized. Judge0 API URL may not be configured."
        )
    return judge0_client
