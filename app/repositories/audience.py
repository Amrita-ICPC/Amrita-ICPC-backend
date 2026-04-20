from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.audience import AudienceNotFoundError
from app.models.audience import Audience, UserAudience
from app.models.user import User
from app.repositories.dto.audience import AudienceRoleCounts, AudienceWithCounts
from app.repositories.dto.pagination import PaginatedResult, PaginationParams
from app.utils.enums import UserRole


class AudienceRepository:
    """Repository for audience persistence operations.

    This repository encapsulates all SQLAlchemy queries and mutations for the
    audience domain. It is intentionally persistence-only and returns ORM
    entities; mapping to DTOs/schemas is handled in the mapper/service layers.
    """

    def __init__(self, db: AsyncSession):
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
        """
        self.db = db

    async def create_audience(self, audience: Audience) -> Audience:
        """Persist a new audience.

        Args:
            audience: Audience ORM entity to persist.

        Returns:
            The persisted Audience entity.
        """
        self.db.add(audience)
        await self.db.flush()
        await self.db.refresh(audience)
        return audience

    async def get_audience_by_id(self, audience_id: UUID) -> Audience | None:
        """Fetch an audience by ID.

        Args:
            audience_id: Audience identifier.

        Returns:
            The Audience entity if found; otherwise, None.
        """
        result = await self.db.execute(
            select(Audience).where(Audience.id == audience_id)
        )
        return result.scalars().first()

    async def get_audience_or_raise(self, audience_id: UUID) -> Audience:
        """Fetch an audience by ID or raise if not found.

        Args:
            audience_id: Audience identifier.

        Returns:
            The Audience entity.

        Raises:
            AudienceNotFoundError: If the audience does not exist.
        """
        audience = await self.get_audience_by_id(audience_id)
        if audience is None:
            raise AudienceNotFoundError(str(audience_id))
        return audience

    async def get_audience_by_name(self, name: str) -> Audience | None:
        """Fetch an audience by its unique name.

        Args:
            name: Audience name.

        Returns:
            The Audience entity if found; otherwise, None.
        """
        result = await self.db.execute(select(Audience).where(Audience.name == name))
        return result.scalars().first()

    async def list_audiences(
        self,
        pagination: PaginationParams,
        *,
        query: str | None = None,
    ) -> PaginatedResult:
        """List audiences with pagination and optional name search.

        Args:
            pagination: Pagination configuration (skip/limit).
            query: Optional case-insensitive substring filter on name.

        Returns:
            PaginatedResult with total count and a list of Audience entities.
        """
        counts_subq = (
            select(
                UserAudience.audience_id.label("audience_id"),
                func.count(func.distinct(UserAudience.user_id))
                .filter(User.role == UserRole.manager)
                .label("manager_count"),
                func.count(func.distinct(UserAudience.user_id))
                .filter(User.role == UserRole.instructor)
                .label("instructor_count"),
                func.count(func.distinct(UserAudience.user_id))
                .filter(User.role == UserRole.student)
                .label("student_count"),
                func.count(func.distinct(UserAudience.user_id))
                .filter(
                    User.role.in_(
                        [
                            UserRole.manager,
                            UserRole.instructor,
                            UserRole.student,
                        ]
                    )
                )
                .label("total_users"),
            )
            .select_from(UserAudience)
            .join(User, User.id == UserAudience.user_id)
            .group_by(UserAudience.audience_id)
            .subquery()
        )

        stmt = select(
            Audience,
            func.coalesce(counts_subq.c.manager_count, 0),
            func.coalesce(counts_subq.c.instructor_count, 0),
            func.coalesce(counts_subq.c.student_count, 0),
            func.coalesce(counts_subq.c.total_users, 0),
        ).outerjoin(counts_subq, counts_subq.c.audience_id == Audience.id)
        count_stmt = select(func.count(Audience.id))

        if query:
            like = f"%{query}%"
            stmt = stmt.where(Audience.name.ilike(like))
            count_stmt = count_stmt.where(Audience.name.ilike(like))

        total = int((await self.db.execute(count_stmt)).scalar() or 0)
        result = await self.db.execute(
            stmt.order_by(Audience.name.asc())
            .offset(pagination.skip)
            .limit(pagination.limit)
        )

        items: list[AudienceWithCounts] = []
        for (
            audience,
            manager_count,
            instructor_count,
            student_count,
            total_users,
        ) in result.all():
            counts = AudienceRoleCounts(
                manager_count=int(manager_count or 0),
                instructor_count=int(instructor_count or 0),
                student_count=int(student_count or 0),
                total_users=int(total_users or 0),
            )
            items.append(AudienceWithCounts(audience=audience, counts=counts))

        return PaginatedResult(total=total, items=items)

    async def get_audience_with_counts(self, audience_id: UUID) -> AudienceWithCounts:
        """Fetch an audience by ID along with membership counts by role.

        Args:
            audience_id: Audience identifier.

        Returns:
            AudienceWithCounts DTO.

        Raises:
            AudienceNotFoundError: If the audience does not exist.
        """
        counts_subq = (
            select(
                UserAudience.audience_id.label("audience_id"),
                func.count(func.distinct(UserAudience.user_id))
                .filter(User.role == UserRole.manager)
                .label("manager_count"),
                func.count(func.distinct(UserAudience.user_id))
                .filter(User.role == UserRole.instructor)
                .label("instructor_count"),
                func.count(func.distinct(UserAudience.user_id))
                .filter(User.role == UserRole.student)
                .label("student_count"),
                func.count(func.distinct(UserAudience.user_id))
                .filter(
                    User.role.in_(
                        [
                            UserRole.manager,
                            UserRole.instructor,
                            UserRole.student,
                        ]
                    )
                )
                .label("total_users"),
            )
            .select_from(UserAudience)
            .join(User, User.id == UserAudience.user_id)
            .where(UserAudience.audience_id == audience_id)
            .group_by(UserAudience.audience_id)
            .subquery()
        )

        stmt = (
            select(
                Audience,
                func.coalesce(counts_subq.c.manager_count, 0),
                func.coalesce(counts_subq.c.instructor_count, 0),
                func.coalesce(counts_subq.c.student_count, 0),
                func.coalesce(counts_subq.c.total_users, 0),
            )
            .outerjoin(counts_subq, counts_subq.c.audience_id == Audience.id)
            .where(Audience.id == audience_id)
        )
        row = (await self.db.execute(stmt)).first()
        if row is None:
            raise AudienceNotFoundError(str(audience_id))

        audience, manager_count, instructor_count, student_count, total_users = row
        counts = AudienceRoleCounts(
            manager_count=int(manager_count or 0),
            instructor_count=int(instructor_count or 0),
            student_count=int(student_count or 0),
            total_users=int(total_users or 0),
        )
        return AudienceWithCounts(audience=audience, counts=counts)

    async def update_audience(self, audience: Audience) -> Audience:
        """Flush and refresh an audience entity.

        Args:
            audience: Audience entity with in-memory updates applied.

        Returns:
            The updated Audience entity.
        """
        await self.db.flush()
        await self.db.refresh(audience)
        return audience

    async def delete_audience(self, audience: Audience) -> None:
        """Delete an audience entity.

        Args:
            audience: Audience entity to delete.
        """
        await self.db.delete(audience)
        await self.db.flush()

    async def add_users_to_audience(
        self, audience_id: UUID, user_ids: list[UUID]
    ) -> None:
        """Add multiple users to an audience.

        This operation is idempotent: existing user links are ignored.

        Args:
            audience_id: Target audience ID.
            user_ids: User IDs to link to the audience.
        """
        unique_user_ids = list(dict.fromkeys(user_ids))

        existing_result = await self.db.execute(
            select(UserAudience.user_id).where(
                UserAudience.audience_id == audience_id,
                UserAudience.user_id.in_(unique_user_ids),
            )
        )
        existing = set(existing_result.scalars().all())

        to_add = [
            UserAudience(user_id=user_id, audience_id=audience_id)
            for user_id in unique_user_ids
            if user_id not in existing
        ]
        if to_add:
            self.db.add_all(to_add)
            await self.db.flush()

    async def remove_users_from_audience(
        self, audience_id: UUID, user_ids: list[UUID]
    ) -> int:
        """Remove multiple users from an audience.

        Args:
            audience_id: Target audience ID.
            user_ids: User IDs to unlink from the audience.

        Returns:
            Number of links removed.
        """
        unique_user_ids = list(dict.fromkeys(user_ids))
        result = await self.db.execute(
            delete(UserAudience).where(
                UserAudience.audience_id == audience_id,
                UserAudience.user_id.in_(unique_user_ids),
            )
        )
        await self.db.flush()
        cursor_result = result  # async execute returns a CursorResult for DML
        if not isinstance(cursor_result, CursorResult):
            return 0
        return int(cursor_result.rowcount or 0)

    async def list_audience_users_page(
        self,
        audience_id: UUID,
        pagination: PaginationParams,
        *,
        role: UserRole | None = None,
    ) -> list[User]:
        """List a single page of users in an audience.

        This method intentionally does not compute total count.

        Args:
            audience_id: Audience identifier.
            pagination: Pagination configuration.

        Returns:
            List of User entities in the requested page.
        """
        stmt = (
            select(User)
            .join(UserAudience, UserAudience.user_id == User.id)
            .where(UserAudience.audience_id == audience_id)
            .order_by(User.name.asc())
            .offset(pagination.skip)
            .limit(pagination.limit)
        )
        if role is not None:
            stmt = stmt.where(User.role == role)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_audience_users(
        self,
        audience_id: UUID,
        *,
        role: UserRole | None = None,
    ) -> int:
        """Count users in an audience, optionally filtered by role.

        Args:
            audience_id: Audience identifier.
            role: Optional role filter.

        Returns:
            Total number of matching users.
        """
        stmt = (
            select(func.count(User.id))
            .select_from(User)
            .join(UserAudience, UserAudience.user_id == User.id)
            .where(UserAudience.audience_id == audience_id)
        )
        if role is not None:
            stmt = stmt.where(User.role == role)
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def get_audience_users_by_user_ids(
        self, audience_id: UUID, user_ids: list[UUID]
    ) -> list[User]:
        """Fetch users in an audience matching a list of user IDs.

        Args:
            audience_id: Audience identifier.
            user_ids: List of user IDs to match.
        Returns:
            List of User entities matching the criteria.
        """
        unique_user_ids = list(dict.fromkeys(user_ids))
        result = await self.db.execute(
            select(User)
            .join(UserAudience, UserAudience.user_id == User.id)
            .where(
                UserAudience.audience_id == audience_id,
                UserAudience.user_id.in_(unique_user_ids),
            )
        )
        users = list(result.scalars().all())
        return users
