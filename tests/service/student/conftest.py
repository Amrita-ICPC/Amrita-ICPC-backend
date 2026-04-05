"""
Fixtures for student service tests.

Fixtures are reusable test data and setup.
"""

import pytest
import pytest_asyncio
from uuid import uuid4
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.user import User
from app.models.contest import Contest
from app.utils.enums import ContestStatus, UserRole


@pytest_asyncio.fixture
async def db_session():
    """
    Create an in-memory SQLite database for testing.
    
    This fixture:
    1. Creates an in-memory database
    2. Creates ONLY necessary tables (avoids foreign key issues)
    3. Provides a session
    4. Cleans up after test
    """
    # Create in-memory SQLite engine
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )

    # Create only the tables we need for student tests
    async with engine.begin() as conn:
        # Disable foreign key constraints
        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        
        # Create ONLY these tables
        await conn.run_sync(User.__table__.create, checkfirst=True)
        await conn.run_sync(Contest.__table__.create, checkfirst=True)

    # Create session factory
    async_session = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Contest.__table__.drop, checkfirst=True)
        await conn.run_sync(User.__table__.drop, checkfirst=True)

    await engine.dispose()


@pytest.fixture
def student_user():
    """Create a mock student user."""
    return User(
        id=uuid4(),
        email="student@amrita.edu",
        name="John Student",
        role=UserRole.STUDENT,
    )


@pytest.fixture
def public_contest():
    """Create a public contest available for registration."""
    now = datetime.utcnow()
    return Contest(
        id=uuid4(),
        name="ICPC Regionals 2026",
        description="Regional finals for ICPC",
        is_public=True,  # ← PUBLIC
        status=ContestStatus.SCHEDULED,
        start_time=now + timedelta(days=10),
        end_time=now + timedelta(days=10, hours=5),
        created_by=uuid4(),
        is_deleted=False,
    )


@pytest.fixture
def private_contest():
    """Create a private contest (hidden from students)."""
    now = datetime.utcnow()
    return Contest(
        id=uuid4(),
        name="Private Contest",
        description="This is private",
        is_public=False,  # ← PRIVATE
        status=ContestStatus.SCHEDULED,
        start_time=now + timedelta(days=10),
        end_time=now + timedelta(days=10, hours=5),
        created_by=uuid4(),
        is_deleted=False,
    )


@pytest.fixture
def completed_contest():
    """Create a completed contest (no new registrations)."""
    now = datetime.utcnow()
    return Contest(
        id=uuid4(),
        name="Completed Contest",
        description="This contest is finished",
        is_public=True,
        status=ContestStatus.COMPLETED,  # ← COMPLETED
        start_time=now - timedelta(days=5),
        end_time=now - timedelta(days=4),
        created_by=uuid4(),
        is_deleted=False,
    )