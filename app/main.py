from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import setup_exception_handlers
from app.api.route import api_router
from app.core.clients.database import init_db
from app.core.clients.redis import close_redis, init_redis
from app.core.config import config
from app.core.logger import logger, setup_sqlalchemy_logging, setup_uvicorn_logging
from app.core.security import setup_security


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup logging
    setup_sqlalchemy_logging()
    setup_uvicorn_logging()
    logger.info(f"Starting application in {config.ENVIRONMENT} mode")
    logger.info(f"API Prefix: {config.API_PREFIX}")

    # Initialize database (create tables) if in development
    init_db()

    # Initialize Redis
    await init_redis()

    yield

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
# Allowing all origins for development
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fastapi_app.include_router(api_router, prefix=config.API_PREFIX)
setup_exception_handlers(fastapi_app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:fastapi_app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=config.ENVIRONMENT == "development",
    )
