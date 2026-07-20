"""
One-off: create a single published, registration-open, INDIVIDUAL-mode
contest, clone every question from the curated DSA bank
(scripts/seed_question_bank.py) into it, and publish results so the
leaderboard is visible - everything the load test's full student journey
needs (dashboard -> start -> questions -> run/submit -> leaderboard).

INDIVIDUAL contest_mode auto-confirms a student's solo team the moment it's
created (team_status=CONFIRMED, approval_status=APPROVED - see
ContestTeamService.create_contest_team), unlike TEAM-mode contests where a
newly created team sits in DRAFT until someone separately confirms it. That
makes INDIVIDUAL mode the right fit for a students-only, no-team-flows load
test: register once, start immediately.

The contest row itself is created DB-direct (same pattern as
scripts/seed_contests.py), since it just needs to insert one row and doesn't
need an authenticated session to do it. Cloning questions from the bank goes
through the real ContestQuestionService.clone_questions_from_bank - unlike a
plain insert, cloning deep-copies each Question (+testcases+templates+tags)
via deep_copy_question_for_clone and enforces bank-read/contest-manage
permission checks, so reusing the platform's own service layer here (wired
up the same way app/api/routes/v1/contest.py's get_contest_question_service
dependency does) is far safer than re-implementing that logic by hand.

Both the contest and the bank must be owned/managed by the same user for the
permission checks to pass trivially (ContestPermission.can_manage_contest:
"creator always allowed"; BankValidator.check_read_bank: owner or direct
share only) - so this script reuses the exact same admin account
scripts/seed_question_bank.py seeds, rather than a separate instructor.

Requires scripts/seed_question_bank.py to have already been run against the
same database - the bank it creates is the source this script clones from.

Usage:
    .venv/bin/python loadtest/setup/setup_contest.py [--days 7]

Prints progress to stdout; the final line is `CONTEST_ID_RESULT=<uuid>` so
calling shell scripts can extract it reliably. NOTE: this environment's
SQLAlchemy engine runs with echo=True (ENVIRONMENT=development), which
interleaves verbose query logging into stdout - a plain `tail -1` is NOT
reliable here (a log line can land last). Extract with e.g.
`grep -oE 'CONTEST_ID_RESULT=[0-9a-fA-F-]+' | tail -1 | cut -d= -f2`.
"""

import argparse
import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Repo root is two levels up from loadtest/setup/ - needed for `app.*` imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import select

from app.core.cache.decorators import defer_cache_invalidation
from app.core.clients.database import SessionLocal
from app.core.guards.contest import ContestOperationGuard
from app.models.bank import Bank
from app.models.contest import Contest
from app.models.user import User
from app.repositories.bank import BankRepository
from app.repositories.contest import ContestRepository
from app.repositories.language import LanguageRepository
from app.repositories.question import QuestionRepository
from app.schema.contest import ContestBankCloneRequest
from app.service.contest_question_service import ContestQuestionService
from app.utils.enums import ContestMode, ContestStatus, TeamApprovalMode, UserRole
from app.validators.contest import ContestValidator
from scripts.seed_question_bank import BANK_NAME


async def get_or_create_admin(session) -> User:
    """Reuse the same admin account scripts/seed_question_bank.py seeds (or
    create one if it doesn't exist yet). The bank must be readable by
    whoever creates+clones-into this contest (see app/validators/bank.py:
    check_read_bank - owner or direct share only), and being the exact same
    user is the simplest way to guarantee both checks pass."""
    result = await session.execute(
        select(User).where(User.role == UserRole.admin).limit(1)
    )
    admin = result.scalars().first()
    if admin:
        return admin

    admin = User(
        id=uuid.uuid4(),
        user_id="loadtest_admin",
        name="Load Test Admin",
        email="loadtest_admin@example.com",
        phone_no="+10000000000",
        role=UserRole.admin,
        created_at=datetime.now(timezone.utc),
        last_updated=datetime.now(timezone.utc),
    )
    session.add(admin)
    await session.flush()
    return admin


async def main(days: int) -> None:
    async with SessionLocal() as session:
        async with defer_cache_invalidation():
            admin = await get_or_create_admin(session)

            bank_result = await session.execute(
                select(Bank).where(
                    Bank.name == BANK_NAME, Bank.created_by == admin.id
                )
            )
            bank = bank_result.scalars().first()
            if not bank:
                print(
                    f"ERROR: bank '{BANK_NAME}' not found for admin {admin.id}. "
                    "Run scripts/seed_question_bank.py against this database first.",
                    file=sys.stderr,
                )
                sys.exit(1)

            now = datetime.now(timezone.utc)
            contest = Contest(
                id=uuid.uuid4(),
                name=f"Load Test Contest [{now:%Y-%m-%d %H:%M UTC}]",
                description="Generated by loadtest/setup/setup_contest.py for load testing.",
                image=None,
                is_public=True,
                max_teams=None,  # unlimited - solo teams for every student
                min_team_size=1,
                max_team_size=1,
                rules="Standard programming contest rules apply",
                registration_start=now - timedelta(days=1),
                registration_end=now + timedelta(days=days),
                team_approval_mode=TeamApprovalMode.AUTO_APPROVE,
                contest_mode=ContestMode.INDIVIDUAL,
                status=ContestStatus.PUBLISHED,
                published_at=now,
                published_by=admin.id,
                created_by=admin.id,
                created_at=now,
                updated_at=now,
                start_time=now - timedelta(hours=1),  # already live
                end_time=now + timedelta(days=days),
                duration=None,
                show_leaderboard_during_contest=True,
                # Student-facing leaderboard visibility is gated by these two
                # fields specifically (app/service/student/contest_team.py:
                # get_contest_leaderboard checks results_published_at + \
                # show_leaderboard, NOT show_leaderboard_during_contest) -
                # set both so loadtest/scenarios/leaderboard_poll_locustfile.py
                # exercises the real 200 path instead of always hitting the
                # ContestResultsNotVisibleError 403.
                results_published_at=now,
                show_leaderboard=True,
                evaluate_on_submit=True,
                participation_type="INDIVIDUAL_WORKSPACE",
                max_submission_per_question=5,
                shuffle_questions=False,
            )
            session.add(contest)
            await session.flush()

            print(f"Created contest '{contest.name}'")

            question_service = ContestQuestionService(
                ContestRepository(session),
                ContestOperationGuard(session),
                ContestValidator(),
                QuestionRepository(session),
                LanguageRepository(session),
                BankRepository(session),
            )
            clone_request = ContestBankCloneRequest(bank_id=bank.id, copy_all=True)
            cloned = await question_service.clone_questions_from_bank(
                contest_id=contest.id,
                request=clone_request,
                user_id=admin.id,
            )
            print(f"Cloned {len(cloned)} questions from bank '{BANK_NAME}'")

            await session.commit()

        print(f"CONTEST_ID_RESULT={contest.id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="How many days the contest should stay open (default 7)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.days))
