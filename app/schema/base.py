from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_serializer

T = TypeVar("T")


class MetaResponse(BaseModel):
    request_id: str
    timestamp: datetime


class PaginationResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool


class APIResponse(BaseModel, Generic[T]):
    success: bool = True
    status: int = 200
    message: str = "Success"
    data: T | None = None
    pagination: Optional[PaginationResponse] = Field(default=None)
    meta: MetaResponse

    model_config = ConfigDict(from_attributes=True)

    @model_serializer(mode="wrap")
    def serialize_model(self, handler):
        res = handler(self)
        if isinstance(res, dict):
            if res.get("pagination") is None:
                res.pop("pagination", None)
            if res.get("data") is None:
                res.pop("data", None)
        return res


class ErrorDetails(BaseModel):
    code: str
    details: list[str] | list[dict] | None = None


class APIErrorResponse(BaseModel):
    success: bool = False
    status: int
    message: str
    error: ErrorDetails | None = None
    meta: MetaResponse
