import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import anyio
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ValidationError
from uuid_extensions import uuid7

from app.core.config import settings
from app.core.errors import AuthError
from app.models.enums import UserRole

TokenType = Literal["access", "refresh"]

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Verified against when the email does not exist, so that a miss costs the same
# as a wrong password and cannot be told apart by timing.
_DUMMY_HASH = _pwd.hash("timing-equaliser")


class TokenClaims(BaseModel):
    sub: UUID
    tid: UUID
    tslug: str
    role: UserRole
    typ: TokenType
    jti: UUID
    exp: int
    iat: int


async def hash_password(password: str) -> str:
    # bcrypt at cost 12 takes a couple hundred milliseconds of CPU, which would
    # stall the event loop for every other request on this worker.
    return await anyio.to_thread.run_sync(_pwd.hash, password)


async def verify_password(password: str, password_hash: str) -> bool:
    return await anyio.to_thread.run_sync(_pwd.verify, password, password_hash)


async def verify_password_dummy(password: str) -> None:
    """Burn the same CPU as a real check, for logins where the email is unknown."""
    await anyio.to_thread.run_sync(_pwd.verify, password, _DUMMY_HASH)


def _encode(
    *,
    user_id: UUID,
    tenant_id: UUID,
    tenant_slug: str,
    role: UserRole,
    kind: TokenType,
    ttl: timedelta,
) -> tuple[str, UUID, datetime]:
    now = datetime.now(UTC)
    expires_at = now + ttl
    jti = uuid7()
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "tslug": tenant_slug,
        "role": role.value,
        # Without this, a refresh token would be accepted as an access token.
        "typ": kind,
        "jti": str(jti),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, jti, expires_at


def create_access_token(*, user_id: UUID, tenant_id: UUID, tenant_slug: str, role: UserRole) -> str:
    token, _, _ = _encode(
        user_id=user_id,
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        role=role,
        kind="access",
        ttl=timedelta(minutes=settings.access_token_ttl_min),
    )
    return token


def create_refresh_token(
    *, user_id: UUID, tenant_id: UUID, tenant_slug: str, role: UserRole
) -> tuple[str, UUID, datetime]:
    return _encode(
        user_id=user_id,
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        role=role,
        kind="refresh",
        ttl=timedelta(days=settings.refresh_token_ttl_days),
    )


def decode_token(token: str, *, expect: TokenType) -> TokenClaims:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        claims = TokenClaims.model_validate(payload)
    except (JWTError, ValidationError) as exc:
        raise AuthError("Invalid token") from exc

    if claims.typ != expect:
        raise AuthError("Invalid token")
    return claims


def hash_token(token: str) -> str:
    """Refresh tokens are stored hashed, so a database dump is not a set of sessions."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_token_family() -> UUID:
    return UUID(str(uuid7()))


def constant_time_equals(a: str, b: str) -> bool:
    return secrets.compare_digest(a, b)
