"""
Seed script for creating contests, banks, and questions.

This script creates:
1. 100 contests
2. 100 question banks
3. 50-70 questions per bank (5000-7000 total questions)
Questions can be manually imported from banks to contests later.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clients.database import SessionLocal
from app.models.bank import Bank, BankQuestion
from app.models.contest import Contest
from app.models.language import Language
from app.models.question import Question, QuestionLanguage, QuestionTemplate, TestCase
from app.models.user import User
from app.utils.enums import (
    ContestMode,
    ContestStatus,
    QuestionDifficulty,
    ScoringType,
    TeamApprovalMode,
    UserRole,
)

# Sample data for generating questions
QUESTION_TEMPLATES = [
    {
        "title": "Array {idx}: Sum Pair",
        "text": "Given an array of integers, find two numbers that sum to a target value.",
    },
    {
        "title": "String {idx}: Palindrome Check",
        "text": "Determine if a given string is a palindrome.",
    },
    {
        "title": "Tree {idx}: Level Order Traversal",
        "text": "Perform level-order traversal on a binary tree.",
    },
    {
        "title": "Graph {idx}: DFS Path",
        "text": "Find a path between two nodes using depth-first search.",
    },
    {
        "title": "DP {idx}: Fibonacci Sequence",
        "text": "Compute the nth Fibonacci number efficiently.",
    },
    {
        "title": "Sort {idx}: Merge Arrays",
        "text": "Merge two sorted arrays into a single sorted array.",
    },
    {
        "title": "Math {idx}: Prime Check",
        "text": "Determine if a number is prime.",
    },
    {
        "title": "String {idx}: Anagram",
        "text": "Check if two strings are anagrams of each other.",
    },
    {
        "title": "Linked List {idx}: Reverse",
        "text": "Reverse a singly linked list.",
    },
    {
        "title": "Hash {idx}: Unique Count",
        "text": "Count unique elements in an array.",
    },
]

DIFFICULTIES = [
    QuestionDifficulty.EASY,
    QuestionDifficulty.EASY,
    QuestionDifficulty.EASY,
    QuestionDifficulty.MEDIUM,
    QuestionDifficulty.MEDIUM,
    QuestionDifficulty.HARD,
]


async def get_or_create_admin(session: AsyncSession) -> User:
    """Get existing admin or create one."""
    result = await session.execute(
        select(User).where(User.role == UserRole.admin).limit(1)
    )
    admin = result.scalars().first()

    if not admin:
        admin = User(
            id=uuid.uuid4(),
            user_id="admin_seed",
            name="System Administrator",
            email="admin_seed@example.com",
            phone_no="+1234567890",
            role=UserRole.admin,
            created_at=datetime.now(timezone.utc),
            last_updated=datetime.now(timezone.utc),
        )
        session.add(admin)
        await session.flush()

    return admin


async def get_or_create_instructor(session: AsyncSession) -> User:
    """Get existing instructor or create one."""
    result = await session.execute(
        select(User).where(User.role == UserRole.instructor).limit(1)
    )
    instructor = result.scalars().first()

    if not instructor:
        instructor = User(
            id=uuid.uuid4(),
            user_id="instructor_seed",
            name="Seed Instructor",
            email="instructor_seed@example.com",
            phone_no="+9876543210",
            role=UserRole.instructor,
            created_at=datetime.now(timezone.utc),
            last_updated=datetime.now(timezone.utc),
        )
        session.add(instructor)
        await session.flush()

    return instructor


async def get_languages(session: AsyncSession) -> list[Language]:
    """Get or create programming languages."""
    result = await session.execute(select(Language))
    languages = result.scalars().all()

    if not languages:
        language_data = [
            {
                "name": "Python 3.11",
                "slug": "python",
                "file_extension": ".py",
                "monaco_language": "python",
            },
            {
                "name": "C++ 17",
                "slug": "cpp",
                "file_extension": ".cpp",
                "monaco_language": "cpp",
            },
            {
                "name": "Java 17",
                "slug": "java",
                "file_extension": ".java",
                "monaco_language": "java",
            },
            {
                "name": "JavaScript",
                "slug": "javascript",
                "file_extension": ".js",
                "monaco_language": "javascript",
            },
        ]

        for idx, lang_data in enumerate(language_data, start=1):
            lang = Language(
                id=idx,
                name=lang_data["name"],
                slug=lang_data["slug"],
                file_extension=lang_data["file_extension"],
                monaco_language=lang_data["monaco_language"],
            )
            session.add(lang)
            languages.append(lang)

        await session.flush()

    return languages


async def create_live_contests(
    session: AsyncSession, instructor: User
) -> list[Contest]:
    """Create 3 live contests with durations of 1, 2, and 3 days."""
    contests = []
    now = datetime.now(timezone.utc)

    print("  Creating 3 live contests...")
    for day_duration in [1, 2, 3]:
        # Contest started a bit in the past to be "live"
        contest_start = now - timedelta(hours=1)
        contest_end = contest_start + timedelta(days=day_duration)

        contest = Contest(
            id=uuid.uuid4(),
            name=f"Live Contest: {day_duration}-Day Challenge",
            description=f"Live programming contest with {day_duration} day(s) duration. Registration open until contest ends.",
            image=None,
            is_public=True,
            max_teams=100,
            min_team_size=1,
            max_team_size=5,
            rules="Standard programming contest rules apply",
            registration_start=now - timedelta(days=7),
            registration_end=contest_end,  # Registration open until contest ends
            scoring_type=ScoringType.AUTO,
            team_approval_mode=TeamApprovalMode.AUTO_APPROVE,
            contest_mode=ContestMode.TEAM,
            status=ContestStatus.PUBLISHED,  # Live/published status
            published_at=now,
            published_by=instructor.id,
            deleted_at=None,
            deleted_by=None,
            created_by=instructor.id,
            created_at=now,
            updated_at=now,
            updated_by=None,
            start_time=contest_start,
            end_time=contest_end,
            duration=None,
            show_leaderboard_during_contest=True,
            evaluate_on_submit=True,
            participation_type="LEADER_ONLY",
            max_submission_per_question=5,
            shuffle_questions=False,
        )
        session.add(contest)
        contests.append(contest)
        print(f"    ✓ Created {day_duration}-day live contest")

    await session.flush()
    print("  ✓ All 3 live contests created")
    return contests


async def create_contests(
    session: AsyncSession, instructor: User, count: int = 100
) -> list[Contest]:
    """Create multiple future contests."""
    contests = []
    now = datetime.now(timezone.utc)

    print(f"  Creating {count} future contests...")
    for i in range(count):
        contest_start = now + timedelta(days=7 + i)
        contest_end = contest_start + timedelta(days=5)
        registration_end = contest_start - timedelta(hours=1)

        contest = Contest(
            id=uuid.uuid4(),
            name=f"Contest {i + 1:03d}: Qualifier Round",
            description=f"Programming contest {i + 1} for skill assessment",
            image=None,
            is_public=True,
            max_teams=100,
            min_team_size=1,
            max_team_size=5,
            rules="Standard programming contest rules apply",
            registration_start=now,
            registration_end=registration_end,
            scoring_type=ScoringType.AUTO,
            team_approval_mode=TeamApprovalMode.AUTO_APPROVE,
            contest_mode=ContestMode.TEAM,
            status=ContestStatus.DRAFT,
            published_at=None,
            published_by=None,
            deleted_at=None,
            deleted_by=None,
            created_by=instructor.id,
            created_at=now,
            updated_at=now,
            updated_by=None,
            start_time=contest_start,
            end_time=contest_end,
            duration=None,
            show_leaderboard_during_contest=True,
            evaluate_on_submit=True,
            participation_type="LEADER_ONLY",
            max_submission_per_question=5,
            shuffle_questions=False,
        )
        session.add(contest)
        contests.append(contest)

        if (i + 1) % 10 == 0:
            print(f"    ✓ Created {i + 1} contests...")

    await session.flush()
    print(f"  ✓ All {count} future contests created")
    return contests


async def create_questions(
    session: AsyncSession,
    instructor: User,
    languages: list[Language],
    questions_per_bank: int = 60,
) -> list[Question]:
    """Create a pool of questions for banks."""
    questions = []
    now = datetime.now(timezone.utc)

    print(f"  Creating {questions_per_bank} questions for each bank...")
    for bank_idx in range(100):
        for q_idx in range(questions_per_bank):
            template = random.choice(QUESTION_TEMPLATES)
            difficulty = random.choice(DIFFICULTIES)

            # Create question
            question = Question(
                id=uuid.uuid4(),
                title=template["title"].format(
                    idx=bank_idx * questions_per_bank + q_idx
                ),
                question_text=template["text"],
                difficulty=difficulty,
                time_limit_ms=random.choice([1000, 2000, 3000, 5000]),
                memory_limit_mb=random.choice([256, 512, 1024, 2048]),
                created_by=instructor.id,
                created_at=now,
                updated_at=now,
            )
            session.add(question)
            questions.append(question)

            # Add language support
            for lang in languages:
                q_lang = QuestionLanguage(
                    question_id=question.id,
                    language_id=lang.id,
                )
                session.add(q_lang)

            # Create test cases
            for tc_idx in range(2):
                test_case = TestCase(
                    id=uuid.uuid4(),
                    question_id=question.id,
                    input=f"test_input_{tc_idx}",
                    output=f"expected_output_{tc_idx}",
                    is_hidden=tc_idx > 0,
                    weight=1,
                    order=tc_idx,
                    created_by=instructor.id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(test_case)

            # Create template for first language
            if languages:
                template_obj = QuestionTemplate(
                    id=uuid.uuid4(),
                    question_id=question.id,
                    language_id=languages[0].id,
                    starter_code="# Starter code for question\n",
                    driver_code=None,
                    solution_code="# Solution code\n",
                )
                session.add(template_obj)

        if (bank_idx + 1) % 10 == 0:
            print(f"    ✓ Created questions for {bank_idx + 1} banks...")
            await session.flush()

    await session.flush()
    print(f"  ✓ All questions created ({len(questions)} total)")
    return questions


async def create_banks(
    session: AsyncSession,
    admin: User,
    questions: list[Question],
    questions_per_bank: int = 60,
) -> list[Bank]:
    """Create banks and assign questions."""
    banks = []
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    print("  Creating banks and assigning questions...")
    question_idx = 0

    for bank_num in range(100):
        bank = Bank(
            id=uuid.uuid4(),
            name=f"Bank {bank_num + 1:03d}: Question Repository [{timestamp}]",
            description=f"Question bank {bank_num + 1} containing {questions_per_bank} problems",
            created_by=admin.id,
            created_at=now,
            updated_at=now,
            is_deleted=False,
            deleted_at=None,
            deleted_by=None,
        )
        session.add(bank)
        banks.append(bank)

        # Assign questions to this bank
        for _ in range(questions_per_bank):
            if question_idx < len(questions):
                bank_question = BankQuestion(
                    id=uuid.uuid4(),
                    bank_id=bank.id,
                    question_id=questions[question_idx].id,
                    created_by=admin.id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(bank_question)
                question_idx += 1

        if (bank_num + 1) % 10 == 0:
            print(f"    ✓ Created {bank_num + 1} banks...")
            await session.flush()

    await session.flush()
    print(f"  ✓ All {len(banks)} banks created with questions assigned")
    return banks


async def main():
    """Main function to seed the database."""
    async with SessionLocal() as session:
        try:
            print("🌱 Starting database seeding...\n")

            # Get or create admin
            print("👨‍💼 Setting up admin...")
            admin = await get_or_create_admin(session)
            print(f"   ✓ Using admin: {admin.name}\n")

            # Get or create instructor
            print("👨‍🏫 Setting up instructor...")
            instructor = await get_or_create_instructor(session)
            print(f"   ✓ Using instructor: {instructor.name}\n")

            # Get or create languages
            print("💻 Setting up programming languages...")
            languages = await get_languages(session)
            print(f"   ✓ {len(languages)} languages available\n")

            # Create 3 live contests (1, 2, 3 days with registration till end)
            print("🔴 Creating live contests...")
            live_contests = await create_live_contests(session, instructor)
            print()

            # Create future contests
            print("🏆 Creating future contests...")
            future_contests = await create_contests(session, instructor, count=100)
            contests = live_contests + future_contests
            print()

            # Determine questions per bank (random between 50-70)
            questions_per_bank = random.randint(50, 70)
            total_questions = 100 * questions_per_bank

            # Create questions
            print(f"❓ Creating questions ({total_questions} total)...")
            questions = await create_questions(
                session, instructor, languages, questions_per_bank
            )
            print()

            # Create banks and assign questions
            print("🏦 Creating banks and assigning questions (Admin as owner)...")
            banks = await create_banks(session, admin, questions, questions_per_bank)
            print()

            # Commit all changes
            await session.commit()
            print("✅ Database seeding completed successfully!\n")
            print("📊 Summary:")
            print(
                f"   • Contests: {len(contests)} total (3 live + 100 future) - Created by: {instructor.name}"
            )
            print(
                "   • Live contests: 1-day, 2-day, 3-day (registration open till end)"
            )
            print(f"   • Banks: {len(banks)} (Owned by: {admin.name})")
            print(f"   • Questions per bank: {questions_per_bank} (50-70 range)")
            print(f"   • Total questions: {len(questions)}")
            print(f"   • Languages: {len(languages)}")
            print("\n💡 Next Steps:")
            print("   1. Import questions from banks to contests via API")
            print("   2. Publish contests when ready")
            print("   3. Create teams and enroll them in contests")

        except Exception as e:
            await session.rollback()
            print(f"\n❌ Error during seeding: {e}")
            import traceback

            traceback.print_exc()
            raise


if __name__ == "__main__":
    asyncio.run(main())
