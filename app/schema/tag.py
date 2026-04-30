from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TagBase(BaseModel):
    name: str = Field(..., max_length=100, description="The name of the tag")


class TagCreate(TagBase):
    pass


class TagUpdate(TagBase):
    pass


class TagResponse(TagBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
