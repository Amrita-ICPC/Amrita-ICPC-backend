from typing import List, Optional
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.contest import Contest, ContestInstructor
from app.schema.contest import ContestCreate, ContestUpdate


class ContestRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, contest_data: ContestCreate, created_by: UUID) -> Contest:
        db_contest = Contest(
            name=contest_data.name,
            description=contest_data.description,
            image=contest_data.image,
            is_public=contest_data.is_public,
            start_time=contest_data.start_time,
            end_time=contest_data.end_time,
            created_by=created_by,
        )
        self.db.add(db_contest)
        self.db.commit()
        self.db.refresh(db_contest)
        return db_contest

    def get_by_id(self, contest_id: UUID) -> Optional[Contest]:
        return self.db.query(Contest).filter(Contest.id == contest_id).first()

    def get_all(
        self, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[int, List[Contest]]:
        base_query = (
            self.db.query(Contest)
            .outerjoin(ContestInstructor)
            .filter(
                or_(
                    Contest.created_by == user_id,
                    ContestInstructor.instructor_id == user_id,
                )
            )
            .distinct()
        )
        total = base_query.count()
        contests = base_query.offset(skip).limit(limit).all()
        return total, contests

    def update(self, contest: Contest, update_data: dict) -> Contest:
        for field, value in update_data.items():
            setattr(contest, field, value)
        self.db.commit()
        self.db.refresh(contest)
        return contest

    def delete(self, contest: Contest) -> None:
        self.db.delete(contest)
        self.db.commit()

    def is_instructor(self, contest_id: UUID, user_id: UUID) -> bool:
        return (
            self.db.query(ContestInstructor)
            .filter(
                ContestInstructor.contest_id == contest_id,
                ContestInstructor.instructor_id == user_id,
            )
            .first()
            is not None
        )
