from typing import cast
from uuid import UUID

from app.exceptions.question import TagAlreadyExistsError
from app.models.tag import Tag
from app.repositories.tag import TagRepository
from app.schema.tag import TagCreate, TagResponse, TagUpdate


class TagService:
    """Service layer for tag management operations.

    This service coordinates tag-related business logic, ensuring name uniqueness
    and delegating database operations to the TagRepository.

    Attributes:
        repository: The repository used for tag database operations.
    """

    def __init__(self, repository: TagRepository):
        """Initialize TagService with a repository.

        Args:
            repository: An instance of TagRepository.
        """
        self.repository = repository

    async def get_tags(self, search: str | None = None) -> list[TagResponse]:
        """List all tags with optional search filtering.

        Args:
            search: Optional string to filter tags by name (partial match).

        Returns:
            list[TagResponse]: A list of validated tag response objects.
        """
        tags = await self.repository.get_all_tags(search)
        return [TagResponse.model_validate(tag) for tag in tags]

    async def create_tag(self, data: TagCreate) -> TagResponse:
        """Create a new tag with a unique name.

        Args:
            data: The tag creation data containing the name.

        Returns:
            TagResponse: The created tag details.

        Raises:
            TagAlreadyExistsError: If a tag with the same name already exists.
        """
        existing = await self.repository.get_tag_by_name(data.name)
        if existing:
            raise TagAlreadyExistsError(data.name)

        tag = Tag(name=data.name)
        created = await self.repository.create_tag(tag)
        return cast(TagResponse, TagResponse.model_validate(created))

    async def update_tag(self, tag_id: UUID, data: TagUpdate) -> TagResponse:
        """Update an existing tag's name.

        Args:
            tag_id: UUID of the tag to update.
            data: The updated tag data.

        Returns:
            TagResponse: The updated tag details.

        Raises:
            TagNotFoundError: If the tag with tag_id does not exist.
            TagAlreadyExistsError: If the new name conflicts with an existing tag.
        """
        tag = await self.repository.get_tag_by_id(tag_id)

        if tag.name != data.name:
            existing = await self.repository.get_tag_by_name(data.name)
            if existing:
                raise TagAlreadyExistsError(data.name)

        tag.name = data.name
        updated = await self.repository.update_tag(tag)
        return cast(TagResponse, TagResponse.model_validate(updated))

    async def delete_tag(self, tag_id: UUID) -> None:
        """Delete an existing tag.

        Args:
            tag_id: UUID of the tag to delete.

        Raises:
            TagNotFoundError: If the tag with tag_id does not exist.
        """
        tag = await self.repository.get_tag_by_id(tag_id)
        await self.repository.delete_tag(tag)
