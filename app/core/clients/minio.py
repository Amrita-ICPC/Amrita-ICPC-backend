from typing import cast

from minio import Minio
from urllib3 import PoolManager
from urllib3.util import Retry, Timeout

from app.core.config import config
from app.core.logger import logger

minio_client: Minio | None = None


def _build_minio_endpoint() -> str:
    return f"{config.MINIO_HOST}:{config.MINIO_PORT}"


def _build_minio_http_client() -> PoolManager:
    """Build a MinIO HTTP client with explicit timeouts and retries.

    The default MinIO/urllib3 retry behavior can wait a very long time when the
    endpoint is unreachable. Keep the timeout short so request failures surface
    quickly instead of hanging for minutes.
    """
    timeout = Timeout(connect=5.0, read=30.0)
    retries = Retry(
        total=2,
        connect=2,
        read=0,
        redirect=0,
        status=0,
        backoff_factor=0.2,
        raise_on_status=False,
    )
    return PoolManager(timeout=timeout, retries=retries)


async def init_minio() -> None:
    """Initialize MinIO client and ensure the default bucket exists."""
    global minio_client

    try:
        endpoint = _build_minio_endpoint()
        logger.info(f"Connecting to MinIO at {endpoint}")

        minio_client = Minio(
            endpoint=endpoint,
            access_key=config.MINIO_ACCESS_KEY,
            secret_key=config.MINIO_SECRET_KEY,
            secure=config.MINIO_SECURE,
            http_client=_build_minio_http_client(),
        )

        bucket_name = config.MINIO_BUCKET_NAME
        if not cast(bool, minio_client.bucket_exists(bucket_name)):
            minio_client.make_bucket(bucket_name)
            logger.info(f"Created MinIO bucket: {bucket_name}")

        logger.info("MinIO connection established successfully.")
    except Exception as error:
        logger.error(f"Failed to connect to MinIO: {error}")
        minio_client = None
        raise


async def close_minio() -> None:
    """Close MinIO client reference."""
    global minio_client
    minio_client = None
    logger.info("MinIO client closed.")


def get_minio_client() -> Minio:
    """Get the initialized MinIO client."""
    if minio_client is None:
        raise RuntimeError("MinIO not initialized")
    return minio_client
