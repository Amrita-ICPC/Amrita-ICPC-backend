from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.errors import setup_exception_handlers
from app.api.route import api_router
from app.core.clients.database import init_db
from app.core.clients.judge0 import close_judge0, init_judge0
from app.core.clients.minio import close_minio, init_minio
from app.core.clients.redis import close_redis, init_redis
from app.core.config import config
from app.core.logger import logger, setup_sqlalchemy_logging, setup_uvicorn_logging
from app.core.middleware import RequestMiddleware
from app.core.rate_limit import init_rate_limiter
from app.core.security import setup_security
from app.core.telemetry import instrument_fastapi_app, setup_telemetry


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup logging
    setup_sqlalchemy_logging()
    setup_uvicorn_logging()
    logger.info(f"Starting application in {config.ENVIRONMENT} mode")
    logger.info(f"API Prefix: {config.API_PREFIX}")

    # Initialize tracing before any client below opens a connection, so
    # their first spans (and the httpx/redis instrumentation) are captured.
    setup_telemetry(config.OTEL_SERVICE_NAME)

    # Initialize database (create tables) if in development
    await init_db()

    # Initialize Redis
    await init_redis()

    # Initialize rate limiter (Redis-backed; must run after init_redis())
    await init_rate_limiter()

    # Initialize MinIO
    await init_minio()

    # Initialize Judge0
    await init_judge0()

    yield

    # Close Judge0
    await close_judge0()

    # Close MinIO
    await close_minio()

    # Close Redis
    await close_redis()

    logger.info("Shutting down application")


fastapi_app = FastAPI(
    title=config.PROJECT_NAME,
    description=config.PROJECT_DESCRIPTION,
    version=config.VERSION,
    lifespan=lifespan,
)

# Setup Security (Authentication)
setup_security(fastapi_app)

# Setup CORS Middleware (Must come AFTER auth middleware setup to run FIRST on requests)
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


fastapi_app.add_middleware(RequestMiddleware)

fastapi_app.include_router(api_router, prefix=config.API_PREFIX)
setup_exception_handlers(fastapi_app)

# Setup Prometheus metrics
Instrumentator(should_instrument_requests_inprogress=True).instrument(
    fastapi_app
).expose(fastapi_app)

# Setup request tracing (no-op if OTEL_EXPORTER_OTLP_ENDPOINT isn't set)
instrument_fastapi_app(fastapi_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:fastapi_app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=config.ENVIRONMENT == "development",
    )
