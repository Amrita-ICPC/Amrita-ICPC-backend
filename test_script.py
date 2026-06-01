import asyncio
import uuid

from app.core.clients.database import async_session_maker
from app.core.guards.contest_student import ContestStudentGuard
from app.core.guards.team_student import TeamStudentGuard
from app.repositories.contest import ContestRepository
from app.repositories.student.contest_team import ContestTeamRepository
from app.repositories.student.team import StudentTeamRepository
from app.service.student.contest_team import ContestTeamService


async def test_import():
    async with async_session_maker() as session:
        # We need a user, team, contest. Let's just create them manually to test the service
        uuid.uuid4()

        # This will fail with constraint errors if we don't have all references,
        # but maybe we can just catch the specific greenlet error.
        ContestTeamService(
            repository=ContestTeamRepository(session),
            team_repository=StudentTeamRepository(session),
            team_student_guard=TeamStudentGuard(session),
            contest_repository=ContestRepository(session),
            contest_student_guard=ContestStudentGuard(session),
        )

        # Instead of calling import_team directly, let's just inspect the team.members issue.
        # We will run this and see if it runs.
        pass


if __name__ == "__main__":
    asyncio.run(test_import())
