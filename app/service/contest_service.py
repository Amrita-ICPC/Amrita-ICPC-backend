from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.exceptions.contest import ContestNotFoundError
from app.models.contest import Contest
from app.schema.contest import ContestCreate, ContestUpdate
from app.utils.contest_cache import ContestCache


class ContestService:
    """Service for contest database operations."""

    @staticmethod
    async def create_contest(db: Session, contest: ContestCreate) -> Contest:
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
        
        # Cache the newly created contest
        await ContestCache.set_contest(db_contest)
        
        return db_contest

    @staticmethod
    async def get_contest_by_id(db: Session, contest_id: UUID) -> Contest:
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
            # Try to get from cache first
            cached_contest = await ContestCache.get_contest(contest_id)
            if cached_contest:
                # Reconstruct Contest object from cached data
                contest = Contest(
                    id=UUID(cached_contest["id"]),
                    name=cached_contest["name"],
                    description=cached_contest["description"],
                    image=cached_contest["image"],
                    is_public=cached_contest["is_public"],
                )
                return contest
            
            # If not in cache, fetch from database
            contest = db.query(Contest).filter(Contest.id == contest_id).first()
            if not contest:
                raise ContestNotFoundError(str(contest_id))
            
            # Cache the contest for future requests
            await ContestCache.set_contest(contest)
            
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
    async def update_contest(
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
        # Fetch contest from database (not cache) to ensure we have latest data
        contest = db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        # Update only provided fields
        update_data = contest_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(contest, field, value)

        db.commit()
        db.refresh(contest)
        
        # Update cache (delete old and set new)
        await ContestCache.update_contest(contest)
        
        return contest

    @staticmethod
    async def delete_contest(db: Session, contest_id: UUID) -> Contest:
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
        
        db.delete(contest)
        db.commit()
        
        # Delete from cache
        await ContestCache.delete_contest(contest_id)
        
        return contest
