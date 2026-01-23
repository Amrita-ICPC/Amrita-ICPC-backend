from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.exceptions.contest import ContestNotFoundError
from app.models.contest import Contest
from app.schema.contest import ContestCreate, ContestUpdate


class ContestService:
    """Service for contest database operations."""

    @staticmethod
    def create_contest(db: Session, contest: ContestCreate) -> Contest:
        """
        Create a new contest in the database.

        Args:
            db: Database session
            contest: Contest creation data

        Returns:
            Created contest object
        """
        db_contest = Contest(
            name=contest.name,
            description=contest.description,
            image=contest.image,
            is_public=contest.is_public,
        )
        db.add(db_contest)
        db.commit()
        db.refresh(db_contest)
        return db_contest

    @staticmethod
    def get_contest_by_id(db: Session, contest_id: UUID) -> Contest:
            """
            Get a contest by its ID.

            Args:
                db: Database session
                contest_id: Contest ID

            Returns:
                Contest object

            Raises:
                ContestNotFoundError: If contest not found
            """
            contest = db.query(Contest).filter(Contest.id == contest_id).first()
            if not contest:
                raise ContestNotFoundError(str(contest_id))
            return contest
    
    @staticmethod
    def get_all_contests(
        db: Session, skip: int = 0, limit: int = 100
    ) -> tuple[int, List[Contest]]:
        """
        Get all contests with pagination.

        Args:
            db: Database session
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (total count, contests list)
        """
        total = db.query(Contest).count()
        contests = db.query(Contest).offset(skip).limit(limit).all()
        return total, contests

    @staticmethod
    def update_contest(
        db: Session, contest_id: UUID, contest_data: ContestUpdate
    ) -> Contest:
        """
        Update an existing contest.

        Args:
            db: Database session
            contest_id: Contest ID
            contest_data: Contest update data

        Returns:
            Updated contest object

        Raises:
            ContestNotFoundError: If contest not found
        """
        db_contest = ContestService.get_contest_by_id(db, contest_id)

        # Update only provided fields
        update_data = contest_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_contest, field, value)

        db.commit()
        db.refresh(db_contest)
        return db_contest

    @staticmethod
    def delete_contest(db: Session, contest_id: UUID) -> Contest:
        """
        Delete a contest.

        Args:
            db: Database session
            contest_id: Contest ID

        Returns:
            Deleted contest object

        Raises:
            ContestNotFoundError: If contest not found
        """
        db_contest = ContestService.get_contest_by_id(db, contest_id)
        db.delete(db_contest)
        db.commit()
        return db_contest
