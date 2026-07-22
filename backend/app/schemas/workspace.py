from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class WorkspaceUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceDetailOut(BaseModel):
    id: UUID
    name: str
    owner_user_id: UUID
    role: str
    created_at: datetime


class WorkspaceListOut(BaseModel):
    items: list[WorkspaceDetailOut]
