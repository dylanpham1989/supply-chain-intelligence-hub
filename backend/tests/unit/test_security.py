from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from jose import jwt

from app.core.config import settings
from app.core.errors import AuthError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.enums import UserRole

TENANT = uuid4()
USER = uuid4()


def _access() -> str:
    return create_access_token(
        user_id=USER, tenant_id=TENANT, tenant_slug="acme", role=UserRole.ANALYST
    )


async def test_password_round_trip() -> None:
    hashed = await hash_password("correct horse battery staple")

    assert hashed != "correct horse battery staple"
    assert await verify_password("correct horse battery staple", hashed) is True
    assert await verify_password("wrong", hashed) is False


async def test_same_password_hashes_differently_each_time() -> None:
    first = await hash_password("same input")
    second = await hash_password("same input")

    assert first != second, "bcrypt should salt every hash"


def test_access_token_carries_the_expected_claims() -> None:
    claims = decode_token(_access(), expect="access")

    assert claims.sub == USER
    assert claims.tid == TENANT
    assert claims.tslug == "acme"
    assert claims.role == UserRole.ANALYST
    assert claims.typ == "access"


def test_refresh_token_is_rejected_where_an_access_token_is_expected() -> None:
    """Without the typ claim a long-lived refresh token would work as a bearer."""
    raw, _, _ = create_refresh_token(
        user_id=USER, tenant_id=TENANT, tenant_slug="acme", role=UserRole.ADMIN
    )

    with pytest.raises(AuthError):
        decode_token(raw, expect="access")


def test_access_token_is_rejected_where_a_refresh_token_is_expected() -> None:
    with pytest.raises(AuthError):
        decode_token(_access(), expect="refresh")


def test_token_signed_with_another_secret_is_rejected() -> None:
    forged = jwt.encode(
        {
            "sub": str(USER),
            "tid": str(TENANT),
            "tslug": "acme",
            "role": "admin",
            "typ": "access",
            "jti": str(uuid4()),
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
        "not-the-real-secret",
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(AuthError):
        decode_token(forged, expect="access")


def test_expired_token_is_rejected() -> None:
    past = datetime.now(UTC) - timedelta(minutes=5)
    expired = jwt.encode(
        {
            "sub": str(USER),
            "tid": str(TENANT),
            "tslug": "acme",
            "role": "viewer",
            "typ": "access",
            "jti": str(uuid4()),
            "iat": int((past - timedelta(minutes=30)).timestamp()),
            "exp": int(past.timestamp()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(AuthError):
        decode_token(expired, expect="access")


def test_garbage_is_rejected_rather_than_raising_something_else() -> None:
    for value in ("", "not.a.token", "a.b.c"):
        with pytest.raises(AuthError):
            decode_token(value, expect="access")


def test_refresh_tokens_are_stored_hashed() -> None:
    raw, _, _ = create_refresh_token(
        user_id=USER, tenant_id=TENANT, tenant_slug="acme", role=UserRole.VIEWER
    )
    digest = hash_token(raw)

    assert raw not in digest
    assert len(digest) == 64
    assert hash_token(raw) == digest
