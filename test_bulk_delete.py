"""
Test script for bulk delete contest questions functionality.

This script demonstrates:
1. Creating a contest
2. Adding multiple questions to the contest
3. Deleting multiple questions at once
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from app.core.clients.database import SessionLocal
from app.core.guards.contest import ContestOperationGuard
from app.models.contest import Contest, ContestQuestion
from app.models.question import Question
from app.models.user import User
from app.repositories.bank import BankRepository
from app.repositories.contest import ContestRepository
from app.repositories.language import LanguageRepository
from app.repositories.question import QuestionRepository
from app.schema.contest import RemoveContestQuestionRequest
from app.service.contest_question_service import ContestQuestionService
from app.utils.enums import (
    ContestMode,
    ContestStatus,
    QuestionDifficulty,
    ScoringType,
    TeamApprovalMode,
    UserRole,
)
from app.validators.contest import ContestValidator


async def setup_test_data():
    """Create test data: user, contest, and questions."""
    async with SessionLocal() as session:
        now = datetime.now(timezone.utc)

        # Create user with unique ID
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            id=uuid.uuid4(),
            user_id=f"test_user_{unique_id}",
            name="Test User",
            email=f"test_{unique_id}@example.com",
            phone_no="+1234567890",
            role=UserRole.instructor,
            created_at=now,
            last_updated=now,
        )
        session.add(user)
        await session.flush()

        # Create contest
        contest = Contest(
            id=uuid.uuid4(),
            name="Test Contest for Bulk Delete",
            description="Testing bulk question deletion",
            image=None,
            is_public=True,
            max_teams=50,
            min_team_size=1,
            max_team_size=5,
            rules="Test rules",
            registration_start=now,
            registration_end=now + timedelta(days=1),
            scoring_type=ScoringType.AUTO,
            team_approval_mode=TeamApprovalMode.AUTO_APPROVE,
            contest_mode=ContestMode.TEAM,
            status=ContestStatus.DRAFT,
            published_at=None,
            published_by=None,
            deleted_at=None,
            deleted_by=None,
            created_by=user.id,
            created_at=now,
            updated_at=now,
            updated_by=None,
            start_time=now + timedelta(days=7),
            end_time=now + timedelta(days=8),
            duration=None,
            show_leaderboard_during_contest=True,
            evaluate_on_submit=True,
            participation_type="LEADER_ONLY",
            max_submission_per_question=5,
        )
        session.add(contest)
        await session.flush()

        # Create questions
        questions = []
        for i in range(5):
            question = Question(
                id=uuid.uuid4(),
                title=f"Test Question {i + 1}",
                question_text=f"This is test question {i + 1}",
                difficulty=QuestionDifficulty.EASY,
                time_limit_ms=1000,
                memory_limit_mb=256,
                created_by=user.id,
                created_at=now,
                updated_at=now,
            )
            session.add(question)
            questions.append(question)

        await session.flush()

        # Link questions to contest
        for order, question in enumerate(questions, start=1):
            contest_question = ContestQuestion(
                contest_id=contest.id,
                question_id=question.id,
                bank_question_id=None,
                max_submission=5,
                created_by=user.id,
                created_at=now,
                updated_at=now,
                order=order,
                duration=None,
                score=100,
            )
            session.add(contest_question)

        await session.commit()

        # Return data with fresh session to ensure it's persisted
        async with SessionLocal() as verify_session:
            result = await verify_session.execute(
                select(User).where(User.id == user.id)
            )
            assert result.scalars().first() is not None

        return {
            "user_id": user.id,
            "contest_id": contest.id,
            "question_ids": [q.id for q in questions],
        }


async def verify_questions_in_contest(contest_id: UUID) -> list[UUID]:
    """Verify questions are in the contest."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(ContestQuestion).where(ContestQuestion.contest_id == contest_id)
        )
        contest_questions = result.scalars().all()
        return [cq.question_id for cq in contest_questions]


async def test_bulk_delete():
    """Test bulk delete functionality."""
    print("\n" + "=" * 60)
    print("🧪 Testing Bulk Delete Contest Questions")
    print("=" * 60)

    # Setup test data
    print("\n📋 Step 1: Setting up test data...")
    test_data = await setup_test_data()
    user_id = test_data["user_id"]
    contest_id = test_data["contest_id"]
    all_question_ids = test_data["question_ids"]

    print(f"   ✓ Created user: {user_id}")
    print(f"   ✓ Created contest: {contest_id}")
    print(f"   ✓ Created questions: {len(all_question_ids)}")

    # Verify all questions are in contest
    print("\n🔍 Step 2: Verifying questions in contest...")
    questions_before = await verify_questions_in_contest(contest_id)
    print(f"   ✓ Questions in contest: {len(questions_before)}")
    for qid in questions_before:
        print(f"     - {qid}")

    # Select 3 questions to delete
    questions_to_delete = all_question_ids[:3]
    remaining_questions = all_question_ids[3:]

    print(f"\n🗑️  Step 3: Deleting {len(questions_to_delete)} questions...")
    print("   Questions to delete:")
    for qid in questions_to_delete:
        print(f"     - {qid}")

    # Perform bulk delete
    async with SessionLocal() as session:
        contest_repository = ContestRepository(session)
        question_repository = QuestionRepository(session)
        language_repository = LanguageRepository(session)
        bank_repository = BankRepository(session)
        guard = ContestOperationGuard(session)
        validator = ContestValidator()

        service = ContestQuestionService(
            repository=contest_repository,
            guard=guard,
            validator=validator,
            question_repository=question_repository,
            language_repository=language_repository,
            bank_repository=bank_repository,
        )

        # Create delete request
        delete_request = RemoveContestQuestionRequest(question_ids=questions_to_delete)

        try:
            # Perform deletion
            await service.remove_questions_from_contest(
                contest_id, delete_request, user_id
            )
            await session.commit()
            print("   ✓ Bulk delete executed successfully")
        except Exception as e:
            await session.rollback()
            print(f"   ✗ Error during deletion: {e}")
            return False

    # Verify deletion
    print("\n✅ Step 4: Verifying deletion...")
    questions_after = await verify_questions_in_contest(contest_id)

    print(f"   Questions remaining: {len(questions_after)}")
    for qid in questions_after:
        print(f"     - {qid}")

    # Check if deletion was successful
    success = len(questions_after) == len(remaining_questions)
    if success:
        print("\n   ✓ Deletion successful!")
        print(f"   ✓ Deleted {len(questions_to_delete)} questions")
        print(f"   ✓ {len(questions_after)} questions remain")
    else:
        print("\n   ✗ Deletion failed!")
        print(f"   ✗ Expected {len(remaining_questions)} questions remaining")
        print(f"   ✗ Found {len(questions_after)} questions")

    return success


async def test_bulk_delete_all_questions():
    """Test deleting all questions at once."""
    print("\n" + "=" * 60)
    print("🧪 Testing Bulk Delete All Questions")
    print("=" * 60)

    # Setup test data
    print("\n📋 Setting up test data...")
    test_data = await setup_test_data()
    user_id = test_data["user_id"]
    contest_id = test_data["contest_id"]
    all_question_ids = test_data["question_ids"]

    print(f"   ✓ Created {len(all_question_ids)} questions")

    # Verify all questions exist
    print("\n🔍 Verifying questions...")
    questions_before = await verify_questions_in_contest(contest_id)
    print(f"   ✓ Found {len(questions_before)} questions in contest")

    # Delete all questions
    print(f"\n🗑️  Deleting all {len(all_question_ids)} questions...")

    async with SessionLocal() as session:
        contest_repository = ContestRepository(session)
        question_repository = QuestionRepository(session)
        language_repository = LanguageRepository(session)
        bank_repository = BankRepository(session)
        guard = ContestOperationGuard(session)
        validator = ContestValidator()

        service = ContestQuestionService(
            repository=contest_repository,
            guard=guard,
            validator=validator,
            question_repository=question_repository,
            language_repository=language_repository,
            bank_repository=bank_repository,
        )

        delete_request = RemoveContestQuestionRequest(question_ids=all_question_ids)

        try:
            await service.remove_questions_from_contest(
                contest_id, delete_request, user_id
            )
            await session.commit()
            print("   ✓ All questions deleted successfully")
        except Exception as e:
            await session.rollback()
            print(f"   ✗ Error: {e}")
            return False

    # Verify all deleted
    print("\n✅ Verifying deletion...")
    questions_after = await verify_questions_in_contest(contest_id)
    print(f"   ✓ Questions remaining: {len(questions_after)}")

    success = len(questions_after) == 0
    if success:
        print("   ✓ All questions successfully deleted!")
    else:
        print(f"   ✗ {len(questions_after)} questions still exist")

    return success


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("🚀 Bulk Delete Contest Questions - Test Suite")
    print("=" * 60)

    # Test 1: Partial deletion
    test1_passed = await test_bulk_delete()

    # Test 2: Delete all
    test2_passed = await test_bulk_delete_all_questions()

    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    print(f"Test 1 (Partial Delete): {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"Test 2 (Delete All): {'✅ PASSED' if test2_passed else '❌ FAILED'}")

    if test1_passed and test2_passed:
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
