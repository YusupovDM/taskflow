from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    owner_id: int
    members_count: int
    created_at: datetime
    updated_at: datetime


class MemberAdd(BaseModel):
    user_id: int


class MemberRead(BaseModel):
    user_id: int
    email: str
    full_name: str
    joined_at: datetime


class ProjectDetail(ProjectRead):
    members: list[MemberRead]
