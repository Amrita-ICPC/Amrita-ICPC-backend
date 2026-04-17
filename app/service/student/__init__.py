"""Student-facing services for contest, team, and code execution operations.

Keep imports here minimal and stable. Avoid importing legacy modules that
aren't used by the current routers, since importing any submodule under
`app.service.student.*` executes this package initializer.
"""

from app.service.student.contests import StudentContestService
from app.service.student.student_run_service import StudentRunService
from app.service.student.teams import StudentTeamService

__all__ = [
    "StudentContestService",
    "StudentTeamService",
    "StudentRunService",
]
