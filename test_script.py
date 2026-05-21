import asyncio
from uuid import uuid4
from app.core.clients.database import async_session_maker
from app.repositories.student.contest_team import ContestTeamRepository
from app.repositories.student.team import StudentTeamRepository
from app.repositories.contest import ContestRepository
from app.core.guards.team_student import TeamStudentGuard
from app.core.guards.contest_student import ContestStudentGuard
from app.service.student.contest_team import ContestTeamService
from app.schema.team import ContestTeamImport
from app.models.team import Team, TeamUser
from app.models.contest import Contest
from datetime import datetime, timezone, timedelta
import uuid

async def test_import():
    async with async_session_maker() as session:
        # We need a user, team, contest. Let's just create them manually to test the service
        user_id = uuid.uuid4()
        
        # This will fail with constraint errors if we don't have all references,
        # but maybe we can just catch the specific greenlet error.
        service = ContestTeamService(
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
