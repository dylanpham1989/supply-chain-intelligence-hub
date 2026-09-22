from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserRole
from app.schemas.types import Email


class UserRead(BaseModel):
    """Fields are listed explicitly so password_hash cannot leak by accident."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: Email
    full_name: str
    role: UserRole
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=200)
    role: UserRole


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(None, min_length=2, max_length=200)
    role: UserRole | None = None
    is_active: bool | None = None
