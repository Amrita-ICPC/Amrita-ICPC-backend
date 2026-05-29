from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.cache.decorators import cache_delete, cache_get, cache_set
from app.exceptions.audience import AudienceAlreadyExistsError
from app.mappers.audience import (
    apply_audience_update,
    build_audience_entity,
    build_create_audience_dto,
    build_update_audience_dto,
    normalize_user_ids,
    to_audience_response,
)
from app.repositories.audience import AudienceRepository
from app.repositories.dto.audience import (
    AudienceUserBulkDataEmail,
)
from app.repositories.dto.pagination import PaginationParams
from app.repositories.user import UserRepository
from app.schema.audience import (
    AudienceAddUsersByEmailResponse,
    AudienceCreate,
    AudienceResponse,
    AudienceUpdate,
    AudienceUsersResponse,
)
from app.schema.audience_brief import AudienceBriefResponse
from app.schema.user import UserResponse
from app.utils.enums import UserRole


class AudienceService:
    """Service layer for audience operations.

    This service coordinates audience CRUD and audience membership changes using
    the repository layer for persistence and mapper layer for DTO/schema
    transformations.
    """

    def __init__(
        self,
        *,
        repository: AudienceRepository,
        user_repository: UserRepository,
    ):
        """Initialize the service.

        Args:
            repository: Audience persistence repository.
            user_repository: User persistence repository (for user existence checks).
        """
        self.repository = repository
        self.user_repository = user_repository

    @cache_delete(
        key_builder=lambda self, payload: [
            "audiences:user:*",
        ],
    )
    @cache_set(
        key_builder=lambda result: f"audience:{result.id}",
        ttl=300,
        from_result=True,
    )
    async def create_audience(self, payload: AudienceCreate) -> AudienceResponse:
        """Create a new audience.

        Args:
            payload: Audience creation request.

        Returns:
            Created audience.

        Raises:
            AudienceAlreadyExistsError: If another audience already uses the same name.
        """
        existing = await self.repository.get_audience_by_name(payload.name)
        if existing is not None:
            raise AudienceAlreadyExistsError(payload.name)

        dto = build_create_audience_dto(payload)
        entity = build_audience_entity(dto)
        try:
            created = await self.repository.create_audience(entity)
        except IntegrityError as e:
            raise AudienceAlreadyExistsError(payload.name) from e
        return to_audience_response(created)

    @cache_get(
        key_builder=lambda self, actor_id, skip, limit, query=None: (
            f"audiences:user:{actor_id}:skip:{skip}:limit:{limit}:q:{query or ''}"
        ),
        ttl=60,
    )
    async def list_audiences(
        self,
        actor_id: UUID,
        skip: int,
        limit: int,
        query: str | None = None,
    ) -> tuple[int, list[AudienceResponse]]:
        """List audiences.

        Args:
            skip: Offset for pagination.
            limit: Page size.
            query: Optional case-insensitive name search.
            actor_id: Admin user ID performing the operation.

        Returns:
            Tuple of total count and audience list.
        """
        result = await self.repository.list_audiences(
            PaginationParams(skip=skip, limit=limit),
            query=query,
        )
        audiences: list[AudienceResponse] = [
            to_audience_response(item.audience, counts=item.counts)
            for item in result.items
        ]
        return result.total, audiences

    @cache_get(
        key_builder=lambda self, actor_id, is_admin, skip, limit, query=None: (
            f"audiences:brief:{'admin' if is_admin else 'user'}:{actor_id}:skip:{skip}:limit:{limit}:q:{query or ''}"
        ),
        ttl=60,
    )
    async def list_audience_briefs_for_actor(
        self,
        actor_id: UUID,
        is_admin: bool,
        skip: int,
        limit: int,
        query: str | None = None,
    ) -> tuple[int, list[AudienceBriefResponse]]:
        """List brief audience objects for the caller.

        For admins, this method lists all audiences. For non-admin users, it lists
        only the audiences the user belongs to.

        Args:
            actor_id: Current caller's database user ID.
            is_admin: Whether the caller should be treated as an admin.
            skip: Offset for pagination.
            limit: Page size.
            query: Optional case-insensitive name search.

        Returns:
            Tuple of total count and a list of AudienceBriefResponse objects.
        """
        if is_admin:
            result = await self.repository.list_audience_briefs(
                PaginationParams(skip=skip, limit=limit),
                query=query,
            )
        else:
            result = await self.repository.list_audience_briefs_for_user(
                actor_id,
                PaginationParams(skip=skip, limit=limit),
                query=query,
            )

        briefs = [
            AudienceBriefResponse(id=item.id, name=item.name, type=item.audience_type)
            for item in result.items
        ]
        return result.total, briefs

    @cache_get(
        key_builder=lambda self, audience_id: f"audience:{audience_id}",
        ttl=300,
    )
    async def get_audience(self, audience_id: UUID) -> AudienceResponse:
        """Fetch a single audience by ID.

        Args:
            audience_id: Audience identifier.

        Returns:
            Audience response.
        """
        audience_with_counts = await self.repository.get_audience_with_counts(
            audience_id
        )
        return to_audience_response(
            audience_with_counts.audience,
            counts=audience_with_counts.counts,
        )

    @cache_delete(
        key_builder=lambda self, audience_id, payload: [
            "audiences:user:*",
        ],
    )
    @cache_set(
        key_builder=lambda result: f"audience:{result.id}",
        ttl=300,
        from_result=True,
    )
    async def update_audience(
        self, audience_id: UUID, payload: AudienceUpdate
    ) -> AudienceResponse:
        """Update an existing audience.

        Args:
            audience_id: Audience identifier.
            payload: Update request payload.

        Returns:
            Updated audience response.

        Raises:
            AudienceAlreadyExistsError: If the requested new name conflicts.
        """
        audience_with_counts = await self.repository.get_audience_with_counts(
            audience_id
        )
        audience = audience_with_counts.audience
        dto = build_update_audience_dto(payload)

        rename_to = (
            dto.name if dto.name is not None and dto.name != audience.name else None
        )

        if dto.name is not None and dto.name != audience.name:
            existing = await self.repository.get_audience_by_name(dto.name)
            if existing is not None and existing.id != audience_id:
                raise AudienceAlreadyExistsError(dto.name)

        apply_audience_update(audience, dto)

        try:
            updated = await self.repository.update_audience(audience)
        except IntegrityError as e:
            if rename_to is not None:
                raise AudienceAlreadyExistsError(rename_to) from e
            raise
        return to_audience_response(updated, counts=audience_with_counts.counts)

    @cache_delete(
        key_builder=lambda self, audience_id: [
            "audiences:user:*",
            f"audience:{audience_id}",
            f"audience_users:user:*:{audience_id}:*",
        ],
    )
    async def delete_audience(self, audience_id: UUID) -> None:
        """Delete an audience.

        Args:
            audience_id: Audience identifier.
        """
        audience = await self.repository.get_audience_or_raise(audience_id)
        await self.repository.delete_audience(audience)

    @cache_delete(
        key_builder=lambda self, audience_id, user_ids: [
            "audiences:user:*",
            f"audience:{audience_id}",
            f"audience_users:user:*:{audience_id}:*",
        ],
    )
    async def add_users_to_audience(
        self, audience_id: UUID, user_ids: list[UUID]
    ) -> None:
        """Add users to an audience in bulk.

        Args:
            audience_id: Audience identifier.
            user_ids: User IDs to add.

        Raises:
            AudienceNotFoundError: If the audience does not exist.
            UserNotFoundError: If any user ID does not exist.
        """
        await self.repository.get_audience_or_raise(audience_id)
        normalized = normalize_user_ids(user_ids)
        await self.user_repository.get_users_or_raise(normalized)
        await self.repository.add_users_to_audience(audience_id, normalized)

    @cache_delete(
        key_builder=lambda self, audience_id, user_ids: [
            "audiences:user:*",
            f"audience:{audience_id}",
            f"audience_users:user:*:{audience_id}:*",
        ],
    )
    async def remove_users_from_audience(
        self, audience_id: UUID, user_ids: list[UUID]
    ) -> int:
        """Remove users from an audience in bulk.

        Args:
            audience_id: Audience identifier.
            user_ids: User IDs to remove.

        Returns:
            Number of links removed.

        Raises:
            AudienceNotFoundError: If the audience does not exist.
            UserNotFoundError: If any user ID does not exist.
        """
        await self.repository.get_audience_or_raise(audience_id)
        normalized = normalize_user_ids(user_ids)
        await self.user_repository.get_users_or_raise(normalized)
        return await self.repository.remove_users_from_audience(audience_id, normalized)

    @cache_get(
        key_builder=lambda self, audience_id, skip, limit, actor_id, role=None, query=None: (
            f"audience_users:user:{actor_id}:{audience_id}:skip:{skip}:limit:{limit}:role:{role or ''}:q:{query or ''}"
        ),
        ttl=60,
    )
    async def list_audience_users(
        self,
        audience_id: UUID,
        skip: int,
        limit: int,
        actor_id: UUID,
        role: UserRole | None = None,
        query: str | None = None,
    ) -> tuple[int, AudienceUsersResponse]:
        """List users in an audience.

        Args:
            audience_id: Audience identifier.
            skip: Offset for pagination.
            limit: Page size.
            actor_id: Admin user ID performing the operation.
            role: Optional role filter for returned users.
            query: Optional sub-string filter applied to name, email, or phone number.

        Returns:
            Tuple of (total_users, AudienceUsersResponse).

        Raises:
            AudienceNotFoundError: If the audience does not exist.
        """
        audience_with_counts = await self.repository.get_audience_with_counts(
            audience_id
        )

        total = await self.repository.count_audience_users(
            audience_id, role=role, query=query
        )
        page_users = await self.repository.list_audience_users_page(
            audience_id,
            PaginationParams(skip=skip, limit=limit),
            role=role,
            query=query,
        )
        users = [UserResponse.model_validate(user) for user in page_users]
        counts = audience_with_counts.counts
        response = AudienceUsersResponse(
            users=users,
            manager_count=counts.manager_count,
            instructor_count=counts.instructor_count,
            student_count=counts.student_count,
        )
        return total, response

    @cache_delete(
        key_builder=lambda self, audience_id, bulk_data: [
            "audiences:user:*",
            f"audience:{audience_id}",
            f"audience_users:user:*:{audience_id}:*",
        ],
    )
    async def add_bulk_users_to_audience_by_email(
        self, audience_id: UUID, bulk_data: AudienceUserBulkDataEmail
    ) -> AudienceAddUsersByEmailResponse:
        """Add users to an audience by their email addresses.

        This method looks up user IDs for the provided emails, creates any missing users,
        and then adds all corresponding user IDs to the audience. It returns the updated
        audience user list with counts.

        Args:
            audience_id: Audience identifier.
            bulk_data: Object containing lists of emails to add for each role.
        Returns:
            Updated audience user list with counts.
        """

        await self.repository.get_audience_or_raise(audience_id)
        emails = list(dict.fromkeys(email.strip() for email in bulk_data.emails))
        users = await self.user_repository.get_users_by_emails(emails)
        missing_emails_count = len(emails) - len(users)

        if users:
            user_ids = set([user.id for user in users])
            existing_users = await self.repository.get_audience_users_by_user_ids(
                audience_id, list(user_ids)
            )
            new_user_ids = list(user_ids - set([user.id for user in existing_users]))
            if new_user_ids:
                await self.repository.add_users_to_audience(audience_id, new_user_ids)

        return AudienceAddUsersByEmailResponse(
            already_present=len(existing_users) if users else 0,
            added=len(new_user_ids) if users else 0,
            not_found=missing_emails_count,
            total=len(emails) if bulk_data.emails else 0,
        )
