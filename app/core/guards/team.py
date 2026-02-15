# app/guards/team_guard.py
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.permissions import ContestPermission, TeamPermission
from app.models.contest import Contest


class TeamOperationGuard:
    def __init__(self, db: Session):
        self.db = db

    def check_create_team(
        self,
        user_id: UUID,
        contest: Contest,
        member_ids: list[UUID],
    ):
        """
        Validates:
        - User has contest management permission
        - All members are eligible students for the contest
        """
        ContestPermission.can_manage_contest(self.db, user_id=user_id, contest=contest)
        TeamPermission.is_student_allowed_for_contest(
            self.db, user_ids=member_ids, contest_id=contest.id
        )
