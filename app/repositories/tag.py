from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.question import TagNotFoundError
from app.models.tag import Tag


class TagRepository:
    """Repository for tag-related database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_tag_by_id(self, tag_id: UUID) -> Tag:
        """Fetch a single tag by its ID or raise if missing."""
        result = await self.db.execute(select(Tag).where(Tag.id == tag_id))
        tag = result.scalars().one_or_none()
        if tag is None:
            raise TagNotFoundError(tag_id)
        return tag

    async def get_tag_by_name(self, name: str) -> Tag | None:
        """Fetch a tag by its name (case-insensitive)."""
        result = await self.db.execute(select(Tag).where(Tag.name.ilike(name)))
        return result.scalars().one_or_none()

    async def get_all_tags(self, search: str | None = None) -> list[Tag]:
        """Retrieve all tags, optionally filtered by name."""
        query = select(Tag)
        if search:
            query = query.where(Tag.name.ilike(f"%{search}%"))

        result = await self.db.execute(query.order_by(Tag.name))
        return list(result.scalars().all())

    async def create_tag(self, tag: Tag) -> Tag:
        """Create a new tag in the database."""
        self.db.add(tag)
        await self.db.flush()
        return tag

    async def update_tag(self, tag: Tag) -> Tag:
        """Update an existing tag."""
        await self.db.flush()
        return tag

    async def delete_tag(self, tag: Tag) -> None:
        """Delete a tag from the database."""
        await self.db.delete(tag)
        await self.db.flush()
