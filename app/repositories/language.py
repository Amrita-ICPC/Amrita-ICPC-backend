from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.question import LanguageConflictError
from app.models.language import Language


class LanguageRepository:
    """Repository for platform language catalog operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, language_id: int) -> Language | None:
        result = await self.db.execute(
            select(Language).where(Language.id == language_id)
        )
        return result.scalars().first()

    async def get_existing_ids(self, language_ids: set[int]) -> set[int]:
        """Return the subset of language IDs that exist in the platform catalog."""
        if not language_ids:
            return set()
        result = await self.db.execute(
            select(Language.id).where(Language.id.in_(language_ids))
        )
        return set(result.scalars().all())

    async def get_by_slug(self, slug: str) -> Language | None:
        result = await self.db.execute(select(Language).where(Language.slug == slug))
        return result.scalars().first()

    async def create_language(
        self,
        *,
        language_id: int,
        name: str,
        slug: str,
        file_extension: str | None,
        monaco_language: str | None,
    ) -> Language:
        language = Language(
            id=language_id,
            name=name,
            slug=slug,
            file_extension=file_extension,
            monaco_language=monaco_language,
        )
        self.db.add(language)
        try:
            await self.db.flush()
            await self.db.refresh(language)
        except IntegrityError as error:
            raise LanguageConflictError(
                f"Platform language conflict for id={language_id} or slug='{slug}'"
            ) from error
        return language

    async def list_languages(self) -> list[Language]:
        result = await self.db.execute(select(Language).order_by(Language.name.asc()))
        return list(result.scalars().all())
