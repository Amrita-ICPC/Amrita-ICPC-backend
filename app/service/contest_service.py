from app.models.contest import ContestInstructor
from typing import List
from uuid import UUID
from app.core.permissions import ContestPermission

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.exceptions.contest import ContestNotFoundError
from app.models.contest import Contest
from app.schema.contest import ContestCreate, ContestUpdate, ContestResponse

from app.core.cache.decorators import cache_set, cache_get, cache_delete


class ContestService:
    """Service for contest database operations."""

    @staticmethod
    @cache_delete(
        key_builder=lambda db, contest, created_by: f"contests:user:{created_by}:*",
    )
    @cache_set(
        key_builder=lambda contest: f"contest:{contest.id}",
        ttl=300,
        from_result=True,
    )
    async def create_contest(
        db: Session, contest: ContestCreate, created_by: UUID
    ) -> ContestResponse:
        """
        Create a new contest in the database.

        Args:
            db: Database session
            contest: Contest creation data
            created_by: User ID creating the contest

        Returns:
            Created contest object
        """
        db_contest = Contest(
            name=contest.name,
            description=contest.description,
            image=contest.image,
            is_public=contest.is_public,
            start_time=contest.start_time,
            end_time=contest.end_time,
            created_by=created_by,
        )
        db.add(db_contest)
        db.commit()
        db.refresh(db_contest)
        
        return ContestResponse.model_validate(db_contest)

    @staticmethod
    @cache_get(
        key_builder=lambda db, contest_id: f"contest:{contest_id}",
        ttl=300,
    )
    async def get_contest_by_id(db: Session, contest_id: UUID) -> ContestResponse:
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

        return ContestResponse.model_validate(contest)

    @staticmethod
    @cache_get(
    key_builder=lambda db, user_id, skip=0, limit=100:
        f"contests:user:{user_id}:skip:{skip}:limit:{limit}",
    ttl=300,
)
    async def get_all_contests(
        db: Session, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[int, List[ContestResponse]]:
        """
        Get all contests with pagination.

        Args:
            db: Database session
            user_id: User ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (total count, contests list)
        """
        base_query = (
        db.query(Contest)
        .outerjoin(ContestInstructor)
        .filter(
            or_(
                Contest.created_by == user_id,
                ContestInstructor.instructor_id == user_id,
            )
        )
        .distinct()
    )

        contests = base_query.offset(skip).limit(limit).all()
        return len(contests), [ContestResponse.model_validate(contest) for contest in contests]

    @staticmethod
    @cache_delete(
        key_builder=lambda db, contest_id, contest_data, user_id: f"contests:user:{user_id}:*",
    )
    @cache_set(
        key_builder=lambda contest: f"contest:{contest.id}",
        ttl=300,
        from_result=True,
    )
    
    async def update_contest(
        db: Session, contest_id: UUID, contest_data: ContestUpdate,user_id:UUID
    ) -> ContestResponse:
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
        # Fetch contest from database (not cache) to ensure we have latest data
        contest = db.query(Contest).filter(Contest.id == contest_id).first()

        if not contest:
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_manage_contest(db, user_id=user_id, contest=contest)

        # Update only provided fields
        update_data = contest_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(contest, field, value)

        db.commit()
        db.refresh(contest)
        
        return ContestResponse.model_validate(contest)

    @staticmethod
    @cache_delete(
        key_builder=lambda db, contest_id, user_id:
            [
                f"contest:{contest_id}",
                f"contests:user:{user_id}:*",
            ]
)
    async def delete_contest(db: Session, contest_id: UUID, user_id: UUID) -> ContestResponse:
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
        # Fetch contest from database
        contest = db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_manage_contest(db, user_id=user_id, contest=contest)
        
        db.delete(contest)
        db.commit()
        
        return ContestResponse.model_validate(contest)
