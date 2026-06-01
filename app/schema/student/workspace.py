from datetime import datetime

from pydantic import BaseModel


class WorkspaceData(BaseModel):
    language_id: int
    source_code: str
    updated_at: datetime


class WorkspacePutRequest(BaseModel):
    language_id: int
    source_code: str
