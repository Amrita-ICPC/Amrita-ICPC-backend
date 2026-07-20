from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.core.cache.decorators import defer_cache_invalidation
from app.core.config import config
from app.core.logger import logger
from app.core.telemetry import instrument_sqlalchemy_engine

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
    # DATABASE_HOST is PgBouncer in transaction-pooling mode in deployed
    # environments (see the Ansible data-services role), which rotates the
    # physical Postgres connection between transactions. asyncpg's default
    # per-connection cache of named prepared statements does not survive
    # that rotation ("prepared statement ... does not exist" errors under
    # load) -- disabling it makes every query use an unnamed prepared
    # statement instead, which is transaction-pooling safe. Harmless (and a
    # no-op difference in practice) against a direct, unpooled Postgres too.
    connect_args={"statement_cache_size": 0},
)

# Every process that imports this module (api + all Celery worker roles)
# gets query spans for free -- the tracer is resolved lazily per-query, so
# this doesn't depend on setup_telemetry() having run yet in this process.
instrument_sqlalchemy_engine(engine)

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
            await sync_db_schemas(conn)
            await conn.run_sync(Base.metadata.create_all)

            logger.info("Database tables synced and created successfully.")


async def get_db():
    """
    Dependency to get a database session.

    Wraps the request in defer_cache_invalidation() so that any @cache_delete
    invalidation triggered by this request's service calls is queued and only
    flushed after the commit below succeeds - not immediately when each
    service method returns, which used to race the commit (see
    defer_cache_invalidation's docstring).
    """
    async with SessionLocal() as db:
        try:
            async with defer_cache_invalidation():
                yield db
                await db.commit()
        except Exception:
            await db.rollback()
            raise


async def sync_db_schemas(conn) -> None:
    """
    Detect changed schemas (tables with modified columns) and drop them
    along with any dependent tables, so they can be recreated by create_all.
    Only allowed in development environment.
    """
    if config.ENVIRONMENT != "development":
        return

    logger.info("Checking for changed database schemas...")

    def _get_tables_to_drop(connection) -> list[str]:
        from sqlalchemy import inspect

        inspector = inspect(connection)
        existing_tables = set(inspector.get_table_names())

        changed_tables = set()

        # 1. Detect tables with column changes
        for table_name, table in Base.metadata.tables.items():
            if table_name not in existing_tables:
                continue

            existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
            model_cols = {col.name for col in table.columns}

            # If there's a mismatch in column names, mark as changed
            if existing_cols != model_cols:
                changed_tables.add(table_name)

        if not changed_tables:
            return []

        # 2. Add dependent tables (tables that have FKs to changed tables)
        tables_to_drop = set(changed_tables)
        for table in Base.metadata.sorted_tables:
            if table.name in tables_to_drop:
                continue
            for fk in table.foreign_keys:
                if fk.column.table.name in tables_to_drop:
                    tables_to_drop.add(table.name)
                    break

        # 3. Return tables to drop in reverse topological order (children first)
        ordered_drop = []
        for table in reversed(Base.metadata.sorted_tables):
            if table.name in tables_to_drop and table.name in existing_tables:
                ordered_drop.append(table.name)

        return ordered_drop

    tables_to_drop = await conn.run_sync(_get_tables_to_drop)

    if tables_to_drop:
        logger.info(
            f"Detected schema changes. Dropping tables: {', '.join(tables_to_drop)}"
        )
        for table_name in tables_to_drop:
            await conn.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE;"))
        logger.info("Changed tables dropped successfully.")
    else:
        logger.info("No schema changes detected.")
