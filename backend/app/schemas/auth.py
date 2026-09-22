import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import UserRole
from app.schemas.types import Email

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(min_length=2, max_length=200)
    tenant_slug: str = Field(min_length=3, max_length=63)
    email: Email
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=200)

    @field_validator("tenant_slug")
    @classmethod
    def _check_slug(cls, value: str) -> str:
        slug = value.strip().lower()
        if not SLUG.match(slug):
            raise ValueError("slug must be lowercase words separated by single hyphens")
        return slug


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_slug: str = Field(min_length=3, max_length=63)
    email: Email
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - oauth2 field name, not a secret
    expires_in: int
    role: UserRole
    tenant_slug: str
