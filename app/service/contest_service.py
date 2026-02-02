from typing import List
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get, cache_set
from app.exceptions.auth import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError, InvalidContestError
from app.repositories.contest_repository import ContestRepository
from app.schema.contest import ContestCreate, ContestResponse, ContestUpdate


class ContestService:
    """Service for contest database operations."""

    def __init__(self, contest_repository: ContestRepository):
        self.repository = contest_repository

    @cache_delete(
        key_builder=lambda self, contest, created_by: f"contests:user:{created_by}:*",
    )
    @cache_set(
        key_builder=lambda contest: f"contest:{contest.id}",
        ttl=300,
        from_result=True,
    )
    async def create_contest(
        self, contest: ContestCreate, created_by: UUID
    ) -> ContestResponse:
        """
        Create a new contest.

        Args:
            contest: Contest creation data
            created_by: User ID creating the contest

        Returns:
            Created contest object
        """
        db_contest = self.repository.create(contest, created_by)
        return ContestResponse.model_validate(db_contest)

    @cache_get(
        key_builder=lambda self, contest_id: f"contest:{contest_id}",
        ttl=300,
    )
    async def get_contest_by_id(self, contest_id: UUID) -> ContestResponse:
        """
        Get a contest by its ID.

        Args:
            contest_id: Contest ID

        Returns:
            Contest object

        Raises:
            ContestNotFoundError: If contest not found
        """
        contest = self.repository.get_by_id(contest_id)
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        return ContestResponse.model_validate(contest)

    @cache_get(
        key_builder=lambda self, user_id, skip=0, limit=100: f"contests:user:{user_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_all_contests(
        self, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[int, List[ContestResponse]]:
        """
        Get all contests with pagination.

        Args:
            user_id: User ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (total count, contests list)
        """
        total, contests = self.repository.get_all(user_id, skip, limit)
        return total, [ContestResponse.model_validate(contest) for contest in contests]

    @cache_delete(
        key_builder=lambda self, contest_id, contest_data, user_id: f"contests:user:{user_id}:*",
    )
    @cache_set(
        key_builder=lambda contest: f"contest:{contest.id}",
        ttl=300,
        from_result=True,
    )
    async def update_contest(
        self, contest_id: UUID, contest_data: ContestUpdate, user_id: UUID
    ) -> ContestResponse:
        """
        Update an existing contest.

        Args:
            contest_id: Contest ID
            contest_data: Contest update data
            user_id: User ID performing update

        Returns:
            Updated contest object

        Raises:
            ContestNotFoundError: If contest not found
            PermissionDeniedError: If user doesn't have permission
            InvalidContestError: If update data is invalid
        """
        contest = self.repository.get_by_id(contest_id)
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        if contest.created_by != user_id and not self.repository.is_instructor(
            contest.id, user_id
        ):
            raise PermissionDeniedError(
                "You do not have permission to manage this contest"
            )

        update_data = contest_data.model_dump(exclude_unset=True)
        new_start = update_data.get("start_time", contest.start_time)
        new_end = update_data.get("end_time", contest.end_time)
        if new_end <= new_start:
            raise InvalidContestError("end_time must be after start_time")

        updated_contest = self.repository.update(contest, update_data)
        return ContestResponse.model_validate(updated_contest)

    @cache_delete(
        key_builder=lambda self, contest_id, user_id: [
            f"contest:{contest_id}",
            f"contests:user:{user_id}:*",
        ]
    )
    async def delete_contest(self, contest_id: UUID, user_id: UUID) -> ContestResponse:
        """
        Delete a contest.

        Args:
            contest_id: Contest ID
            user_id: User ID performing delete

        Returns:
            Deleted contest object

        Raises:
            ContestNotFoundError: If contest not found
            PermissionDeniedError: If user doesn't have permission
        """
        contest = self.repository.get_by_id(contest_id)
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        if contest.created_by != user_id and not self.repository.is_instructor(
            contest.id, user_id
        ):
            raise PermissionDeniedError(
                "You do not have permission to manage this contest"
            )

        response = ContestResponse.model_validate(contest)
        self.repository.delete(contest)

        return response
