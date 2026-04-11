"""Judge0 API client for async code execution."""

from typing import Any, Optional

import httpx

from app.core.config import config
from app.core.logger import logger

# Global async client instance
judge0_client: Optional[httpx.AsyncClient] = None


async def init_judge0() -> None:
    """Initialize Judge0 HTTP client."""
    global judge0_client

    if not config.JUDGE0_API_URL:
        logger.warning("JUDGE0_API_URL not set. Judge0 client will not be initialized.")
        return

    try:
        # Build headers with optional API key
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }

        # Only add API key if provided
        if config.JUDGE0_API_KEY:
            headers["X-Auth-Token"] = config.JUDGE0_API_KEY
            logger.info("Judge0 authenticated client configured")
        else:
            logger.warning(
                "JUDGE0_API_KEY not set. Using unauthenticated Judge0 requests."
            )

        # Create persistent async client with connection pooling
        judge0_client = httpx.AsyncClient(
            base_url=config.JUDGE0_API_URL.rstrip("/"),
            headers=headers,
            timeout=config.JUDGE0_API_TIMEOUT,
        )

        logger.info(
            f"Judge0 client initialized: {config.JUDGE0_API_URL} (timeout={config.JUDGE0_API_TIMEOUT}s)"
        )

    except Exception as e:
        logger.error(f"Failed to initialize Judge0 client: {str(e)}")
        judge0_client = None
        raise


async def close_judge0() -> None:
    """Close Judge0 client connection."""
    global judge0_client
    if judge0_client is not None:
        await judge0_client.aclose()
        logger.info("Judge0 client closed.")
        judge0_client = None


def get_judge0_client() -> httpx.AsyncClient:
    """Get Judge0 client instance.
    
    Raises:
        RuntimeError: If client not initialized
    """
    if judge0_client is None:
        raise RuntimeError("Judge0 client not initialized. Call init_judge0() first.")
    return judge0_client