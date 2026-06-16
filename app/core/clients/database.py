import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.core.config import config
from app.core.logger import logger

# Import all models to ensure they are registered with Base.metadata
from app.models.base import Base

# Construct the database URL
DATABASE_URL = f"postgresql+asyncpg://{config.DATABASE_USERNAME}:{config.DATABASE_PASSWORD}@{config.DATABASE_HOST}:{config.DATABASE_PORT}/{config.DATABASE_NAME}"

engine = create_async_engine(
    DATABASE_URL,
    echo=config.ENVIRONMENT == "development",
    pool_pre_ping=True,
    pool_size=config.DATABASE_POOL_SIZE,
    max_overflow=config.DATABASE_MAX_OVERFLOW,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


async def init_db():
    """
    Initialize the database.
    If in development environment, create all tables.
    """
    if config.ENVIRONMENT == "development":
        logger.info("Initializing database...")
        logger.info("Migrations enabled; creating tables via metadata.")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # await drop_db()

            logger.info("Database tables created successfully.")


async def get_db():
    """
    Dependency to get a database session.
    """
    async with SessionLocal() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def drop_db() -> None:
    """
    Drop all database tables dynamically with CASCADE.
    Only allowed in development environment.
    """
    if config.ENVIRONMENT != "development":
        logger.warning("Drop DB operation is only allowed in development environment.")
        return

    logger.info("Dropping database tables...")
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f"DROP TABLE IF EXISTS {table.name} CASCADE;"))
            logger.info(f"Dropped table {table.name} (CASCADE).")
    logger.info("Database tables dropped successfully.")


if __name__ == "__main__":

    async def main() -> None:
        await drop_db()

    asyncio.run(main())
    asyncio.run(main())
