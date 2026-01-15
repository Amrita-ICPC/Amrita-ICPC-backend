from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import config
from app.models.base import Base
from app.core.logger import logger

# Import all models to ensure they are registered with Base.metadata
from app.models.user import User
from app.models.team import Team, TeamUser
from app.models.bank import Bank, BankQuestion
from app.models.question import Question
from app.models.contest import Contest, ContestQuestion, ContestTeam
from app.models.tag import Tag, QuestionTag

# Construct the database URL
DATABASE_URL = f"postgresql://{config.DATABASE_USERNAME}:{config.DATABASE_PASSWORD}@{config.DATABASE_HOST}:{config.DATABASE_PORT}/{config.DATABASE_NAME}"

engine = create_engine(
    DATABASE_URL,
    echo=config.ENVIRONMENT == "development",
    pool_pre_ping=True,
    pool_size=config.DATABASE_POOL_SIZE,
    max_overflow=config.DATABASE_MAX_OVERFLOW,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

def init_db():
    """
    Initialize the database.
    If in development environment, create all tables.
    """
    if config.ENVIRONMENT == "development":
        logger.info("Initializing database...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully.")

def get_db():
    """
    Dependency to get a database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
