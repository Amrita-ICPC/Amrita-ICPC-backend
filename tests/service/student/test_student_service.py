"""
Tests for StudentService.

These test the business logic layer.
"""

import pytest
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.student import StudentRepository
from app.repositories.contest import ContestRepository
from app.repositories.team import TeamRepository
from app.core.guards.student import StudentOperationGuard
from app.validators.student import StudentValidator, StudentRegistrationException
from app.service.student_service import StudentService
from app.exceptions.contest import ContestNotFoundError


class TestGetPublicContests:
    """Test getting public contests."""

    @pytest.mark.asyncio
    async def test_get_public_contests_returns_only_public(
        self, db_session: AsyncSession, public_contest, private_contest
    ):
        """
        Test that get_public_contests returns ONLY public contests.
        
        **Scenario:**
        1. Insert both public and private contests in DB
        2. Call service.get_public_contests()
        3. Assert only public contest returned
        """
        # Add both contests to DB
        db_session.add(public_contest)
        db_session.add(private_contest)
        await db_session.commit()

        # Create service
        student_repo = StudentRepository(db_session)
        contest_repo = ContestRepository(db_session)
        team_repo = TeamRepository(db_session)
        guard = StudentOperationGuard(db_session)
        validator = StudentValidator()

        service = StudentService(
            student_repo, contest_repo, team_repo, guard, validator, db_session
        )

        # Call service
        total, contests = await service.get_public_contests()

        # Assert
        assert total == 1, "Should return exactly 1 public contest"
        assert len(contests) == 1, "List should have 1 contest"
        assert contests[0].id == public_contest.id, "Should return public contest"
        assert contests[0].name == "ICPC Regionals 2026"

    @pytest.mark.asyncio
    async def test_get_public_contests_with_search_filter(
        self, db_session: AsyncSession, public_contest
    ):
        """
        Test that search filter works.
        
        **Scenario:**
        1. Add contest to DB
        2. Search for "ICPC"
        3. Assert contest found
        4. Search for "NonExistent"
        5. Assert no results
        """
        db_session.add(public_contest)
        await db_session.commit()

        student_repo = StudentRepository(db_session)
        contest_repo = ContestRepository(db_session)
        team_repo = TeamRepository(db_session)
        guard = StudentOperationGuard(db_session)
        validator = StudentValidator()

        service = StudentService(
            student_repo, contest_repo, team_repo, guard, validator, db_session
        )

        # Search for existing
        total, contests = await service.get_public_contests(search_term="ICPC")
        assert total == 1
        assert len(contests) == 1

        # Search for non-existent
        total, contests = await service.get_public_contests(search_term="NonExistent")
        assert total == 0
        assert len(contests) == 0

    @pytest.mark.asyncio
    async def test_get_public_contests_with_pagination(
        self, db_session: AsyncSession, public_contest
    ):
        """
        Test that pagination works.
        
        **Scenario:**
        1. Add 25 contests to DB
        2. Get page 1 (limit=10)
        3. Assert 10 results, total=25
        4. Get page 2
        5. Assert 10 results, total=25
        6. Get page 3
        7. Assert 5 results, total=25
        """
        # Add 25 contests
        for i in range(25):
            contest = Contest(
                id=uuid4(),
                name=f"Contest {i+1}",
                description="Test contest",
                is_public=True,
                status=ContestStatus.SCHEDULED,
                start_time=datetime.utcnow() + timedelta(days=10),
                end_time=datetime.utcnow() + timedelta(days=10, hours=5),
                created_by=uuid4(),
                is_deleted=False,
            )
            db_session.add(contest)
        
        await db_session.commit()

        student_repo = StudentRepository(db_session)
        contest_repo = ContestRepository(db_session)
        team_repo = TeamRepository(db_session)
        guard = StudentOperationGuard(db_session)
        validator = StudentValidator()

        service = StudentService(
            student_repo, contest_repo, team_repo, guard, validator, db_session
        )

        # Page 1
        total, contests = await service.get_public_contests(skip=0, limit=10)
        assert total == 25
        assert len(contests) == 10

        # Page 2
        total, contests = await service.get_public_contests(skip=10, limit=10)
        assert total == 25
        assert len(contests) == 10

        # Page 3
        total, contests = await service.get_public_contests(skip=20, limit=10)
        assert total == 25
        assert len(contests) == 5


class TestGetPublicContestById:
    """Test getting a single public contest."""

    @pytest.mark.asyncio
    async def test_get_public_contest_success(
        self, db_session: AsyncSession, public_contest
    ):
        """
        Test successfully retrieving a public contest.
        
        **Scenario:**
        1. Add public contest to DB
        2. Get by ID
        3. Assert found and correct
        """
        db_session.add(public_contest)
        await db_session.commit()

        student_repo = StudentRepository(db_session)
        contest_repo = ContestRepository(db_session)
        team_repo = TeamRepository(db_session)
        guard = StudentOperationGuard(db_session)
        validator = StudentValidator()

        service = StudentService(
            student_repo, contest_repo, team_repo, guard, validator, db_session
        )

        contest = await service.get_public_contest_by_id(public_contest.id)

        assert contest is not None
        assert contest.id == public_contest.id
        assert contest.name == "ICPC Regionals 2026"

    @pytest.mark.asyncio
    async def test_get_public_contest_not_found(
        self, db_session: AsyncSession
    ):
        """
        Test that getting non-existent contest raises error.
        
        **Scenario:**
        1. Try to get contest that doesn't exist
        2. Assert ContestNotFoundError raised
        """
        student_repo = StudentRepository(db_session)
        contest_repo = ContestRepository(db_session)
        team_repo = TeamRepository(db_session)
        guard = StudentOperationGuard(db_session)
        validator = StudentValidator()

        service = StudentService(
            student_repo, contest_repo, team_repo, guard, validator, db_session
        )

        with pytest.raises(ContestNotFoundError):
            await service.get_public_contest_by_id(uuid4())

    @pytest.mark.asyncio
    async def test_get_private_contest_not_visible(
        self, db_session: AsyncSession, private_contest
    ):
        """
        Test that private contests are NOT returned.
        
        **Scenario:**
        1. Add private contest to DB
        2. Try to get it by ID
        3. Assert ContestNotFoundError (hidden)
        """
        db_session.add(private_contest)
        await db_session.commit()

        student_repo = StudentRepository(db_session)
        contest_repo = ContestRepository(db_session)
        team_repo = TeamRepository(db_session)
        guard = StudentOperationGuard(db_session)
        validator = StudentValidator()

        service = StudentService(
            student_repo, contest_repo, team_repo, guard, validator, db_session
        )

        with pytest.raises(ContestNotFoundError):
            await service.get_public_contest_by_id(private_contest.id)


class TestStudentValidator:
    """Test student validator business rules."""

    def test_validate_team_name_empty(self):
        """Test that empty team name is rejected."""
        with pytest.raises(StudentRegistrationException) as exc_info:
            StudentValidator.validate_team_name("")
        assert "Team name cannot be empty" in str(exc_info.value)

    def test_validate_team_name_too_long(self):
        """Test that team name > 100 chars is rejected."""
        long_name = "A" * 101
        with pytest.raises(StudentRegistrationException) as exc_info:
            StudentValidator.validate_team_name(long_name)
        assert "100 characters" in str(exc_info.value)

    def test_validate_team_name_valid(self):
        """Test that valid team name passes."""
        StudentValidator.validate_team_name("Alpha Squad")  # Should not raise

    def test_validate_member_emails_invalid_format(self):
        """Test that invalid email format is rejected."""
        with pytest.raises(StudentRegistrationException) as exc_info:
            StudentValidator.validate_member_emails(["invalid-email"])
        assert "Invalid email format" in str(exc_info.value)

    def test_validate_member_emails_valid(self):
        """Test that valid emails pass."""
        StudentValidator.validate_member_emails(["john@amrita.edu"])  # Should not raise

    def test_validate_team_size_too_large(self):
        """Test that team > 3 members is rejected."""
        with pytest.raises(StudentRegistrationException) as exc_info:
            StudentValidator.validate_team_size(5, max_size=3)
        assert "cannot have more than" in str(exc_info.value)

    def test_validate_team_size_valid(self):
        """Test that valid team size passes."""
        StudentValidator.validate_team_size(3, max_size=3)  # Should not raise


# Add imports at top if missing:
from app.utils.enums import ContestStatus
from datetime import datetime, timedelta
from app.models.contest import Contest