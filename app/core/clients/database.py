from typing import Dict, List, Optional, Set, Type

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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
        if config.MIGRATIONS_ENABLED:
            logger.info("Migrations enabled; creating tables via metadata.")
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        else:
            logger.info("Migrations disabled; running schema sync.")
            async with engine.begin() as conn:

                def run_sync_schema(sync_conn):
                    sync = SchemaSync(sync_conn, Base)
                    # Sync schema (checks all models by default)
                    sync.sync_schema()

                await conn.run_sync(run_sync_schema)
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


class SchemaSync:
    """Sync database schema to SQLAlchemy models with dependency awareness."""

    def __init__(self, engine, base):
        """Initialize a schema sync helper for a given engine/connection and model base."""
        self.engine = engine
        self.base = base
        self.inspector = inspect(engine)

    def get_table_info(self, table_name: str) -> Optional[Dict]:
        """Return columns, foreign keys, and indexes for a table if it exists."""
        if not self.inspector.has_table(table_name):
            return None

        columns = {}
        for col in self.inspector.get_columns(table_name):
            columns[col["name"]] = {
                "type": str(col["type"]),
                "nullable": col["nullable"],
                "default": col.get("default"),
            }

        # Get foreign keys
        foreign_keys = self.inspector.get_foreign_keys(table_name)

        # Get indexes
        indexes = self.inspector.get_indexes(table_name)

        return {"columns": columns, "foreign_keys": foreign_keys, "indexes": indexes}

    def has_table_changed(self, model_class: Type) -> bool:
        """
        Check if model schema differs from database schema.
        Returns True if table doesn't exist or schema has changed.
        """
        table_name = model_class.__tablename__

        # Table doesn't exist
        db_info = self.get_table_info(table_name)
        if db_info is None:
            logger.info(f"Table '{table_name}' does not exist")
            return True

        # Get model columns
        model_columns = {}
        for col in model_class.__table__.columns:
            model_columns[col.name] = {
                "type": str(col.type),
                "nullable": col.nullable,
                "default": col.default,
            }

        db_columns = db_info["columns"]

        # Check if column sets differ
        db_col_names = set(db_columns.keys())
        model_col_names = set(model_columns.keys())

        if db_col_names != model_col_names:
            added = model_col_names - db_col_names
            removed = db_col_names - model_col_names
            if added:
                logger.info(f"Table '{table_name}': columns added: {added}")
            if removed:
                logger.info(f"Table '{table_name}': columns removed: {removed}")
            return True

        # Check if column types changed
        for col_name in model_col_names:
            db_type = db_columns[col_name]["type"]
            model_type = model_columns[col_name]["type"]

            # Normalize type comparison (handle VARCHAR(50) vs VARCHAR etc.)
            if not self._types_equal(db_type, model_type):
                logger.info(
                    f"Table '{table_name}': column '{col_name}' type changed: {db_type} -> {model_type}"
                )
                return True

            # Check nullable
            if db_columns[col_name]["nullable"] != model_columns[col_name]["nullable"]:
                logger.info(
                    f"Table '{table_name}': column '{col_name}' nullable changed"
                )
                return True

        return False

    def _types_equal(self, db_type: str, model_type: str) -> bool:
        """Compare database type with model type using normalized names."""
        # Remove length specifications for comparison
        db_base = db_type.split("(")[0].upper()
        model_base = model_type.split("(")[0].upper()

        # Handle common type equivalences
        type_mappings = {
            "INTEGER": ["INT", "INTEGER"],
            "VARCHAR": ["VARCHAR", "STRING"],
            "TEXT": [
                "TEXT",
            ],
            "BOOLEAN": ["BOOLEAN", "BOOL"],
            "DATETIME": ["DATETIME", "TIMESTAMP"],
        }

        for canonical, equivalents in type_mappings.items():
            if db_base in equivalents and model_base in equivalents:
                return True

        return db_base == model_base

    def get_dependencies(self) -> Dict[str, Set[str]]:
        """
        Build dependency graph: table_name -> set of tables it depends on.
        A table depends on another if it has a foreign key to it.
        """
        dependencies = {}

        for table_name, table in self.base.metadata.tables.items():
            deps = set()
            for fk in table.foreign_keys:
                # fk.column.table.name gives the referenced table name
                referenced_table = fk.column.table.name
                if referenced_table != table_name:  # Skip self-references
                    deps.add(referenced_table)
            dependencies[table_name] = deps

        return dependencies

    def topological_sort(self, tables_to_sort: Set[str]) -> List[str]:
        """
        Sort tables in dependency order (dependent tables first).
        Returns list of table names safe for dropping (children before parents).
        """
        dependencies = self.get_dependencies()

        # Filter to only tables we care about
        filtered_deps = {
            table: deps & tables_to_sort
            for table, deps in dependencies.items()
            if table in tables_to_sort
        }

        sorted_tables = []
        visited = set()

        def visit(table):
            if table in visited:
                return
            visited.add(table)

            # Visit dependencies first (tables this table depends on)
            for dep in filtered_deps.get(table, set()):
                visit(dep)

            sorted_tables.append(table)

        for table in tables_to_sort:
            visit(table)

        # Reverse to get drop order (children first)
        return list(reversed(sorted_tables))

    def get_dependent_tables(self, table_name: str) -> Set[str]:
        """
        Get all tables that depend on the given table (directly or indirectly).
        """
        dependencies = self.get_dependencies()
        dependents = set()

        def find_dependents(target):
            for table, deps in dependencies.items():
                if target in deps and table not in dependents:
                    dependents.add(table)
                    find_dependents(table)  # Recursively find dependents

        find_dependents(table_name)
        return dependents

    def sync_schema(self, models_to_check: List[Type] = None):
        """
        Synchronize schema with models:
        1. Check which tables have changed
        2. Find all dependent tables
        3. Drop in correct order
        4. Recreate tables
        """
        logger.info("Starting schema sync...")

        # If no models specified, check all models
        if models_to_check is None:
            models_to_check = [mapper.class_ for mapper in self.base.registry.mappers]

        # Find changed tables
        changed_models = []
        changed_table_names = set()

        for model in models_to_check:
            if self.has_table_changed(model):
                changed_models.append(model)
                changed_table_names.add(model.__tablename__)

        if not changed_models:
            logger.info("No schema changes detected. Creating missing tables...")
            self.base.metadata.create_all(bind=self.engine)
            logger.info("Schema is up to date.")
            return

        # Find all tables that need to be recreated (changed + dependents)
        tables_to_recreate = set(changed_table_names)

        for table_name in changed_table_names:
            dependents = self.get_dependent_tables(table_name)
            if dependents:
                logger.info(f"Table '{table_name}' has dependents: {dependents}")
                tables_to_recreate.update(dependents)

        logger.info(f"Tables to recreate: {tables_to_recreate}")

        # Sort in dependency order (for dropping)
        drop_order = self.topological_sort(tables_to_recreate)

        try:
            # Drop tables in dependency order
            logger.info(f"Dropping tables in order: {drop_order}")
            for table_name in drop_order:
                if self.inspector.has_table(table_name):
                    table = self.base.metadata.tables[table_name]
                    table.drop(self.engine)
                    logger.info(f"Dropped table: {table_name}")

            # Recreate tables (reverse order - parents first)
            logger.info(f"Creating tables in order: {list(reversed(drop_order))}")
            for table_name in reversed(drop_order):
                table = self.base.metadata.tables[table_name]
                table.create(self.engine)
                logger.info(f"Created table: {table_name}")

            # Ensure all other tables exist
            self.base.metadata.create_all(bind=self.engine)

            logger.info("Schema sync completed successfully!")

        except SQLAlchemyError as e:
            logger.error(f"Error during schema sync: {e}")
            raise
