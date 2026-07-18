import asyncio

from minio import Minio
from urllib3 import PoolManager
from urllib3.util import Retry, Timeout

from app.core.config import config
from app.core.logger import logger

minio_client: Minio | None = None
minio_presign_client: Minio | None = None


def _build_minio_endpoint(host: str, port: int) -> str:
    return f"{host}:{port}"


def _build_minio_public_endpoint() -> str:
    host = config.MINIO_PUBLIC_HOST or config.MINIO_HOST
    port = config.MINIO_PUBLIC_PORT or config.MINIO_PORT
    return _build_minio_endpoint(host, port)


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
    global minio_client, minio_presign_client

    try:
        endpoint = _build_minio_endpoint(config.MINIO_HOST, config.MINIO_PORT)
        public_endpoint = _build_minio_public_endpoint()
        logger.info(f"Connecting to MinIO at {endpoint}")

        minio_client = Minio(
            endpoint=endpoint,
            access_key=config.MINIO_ACCESS_KEY,
            secret_key=config.MINIO_SECRET_KEY,
            secure=config.MINIO_SECURE,
            http_client=_build_minio_http_client(),
        )
        minio_presign_client = (
            minio_client
            if public_endpoint == endpoint
            else Minio(
                endpoint=public_endpoint,
                access_key=config.MINIO_ACCESS_KEY,
                secret_key=config.MINIO_SECRET_KEY,
                secure=config.MINIO_SECURE,
                http_client=_build_minio_http_client(),
            )
        )

        bucket_name = config.MINIO_BUCKET_NAME
        assert minio_client is not None

        def _ensure_bucket(client: Minio, name: str) -> bool:
            if not client.bucket_exists(name):
                client.make_bucket(name)
                return True
            return False

        created = await asyncio.to_thread(_ensure_bucket, minio_client, bucket_name)
        if created:
            logger.info(f"Created MinIO bucket: {bucket_name}")

        logger.info("MinIO connection established successfully.")
    except Exception as error:
        logger.error(f"Failed to connect to MinIO: {error}")
        minio_client = None
        minio_presign_client = None
        raise


async def close_minio() -> None:
    """Close MinIO client references."""
    global minio_client, minio_presign_client
    minio_client = None
    minio_presign_client = None
    logger.info("MinIO clients closed.")


def get_minio_client() -> Minio:
    """Get the initialized MinIO client."""
    if minio_client is None:
        raise RuntimeError("MinIO not initialized")
    return minio_client


def get_minio_presign_client() -> Minio:
    """Get the MinIO client configured for browser-facing presigned URLs."""
    if minio_presign_client is None:
        raise RuntimeError("MinIO presign client not initialized")
    return minio_presign_client
