"""Signup, login, refresh rotation, reuse detection and logout, end to end."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

SIGNUP = {
    "company_name": "Northwind Freight",
    "tenant_slug": "northwind-freight",
    "email": "founder@northwind.test",
    "password": "correct horse battery",
    "full_name": "Ada Founder",
}
REFRESH_PATH = "/api/v1/auth/refresh"


async def _signup(api: AsyncClient, **overrides: object) -> dict:
    response = await api.post("/api/v1/auth/signup", json={**SIGNUP, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_signup_creates_a_workspace_with_an_admin(api: AsyncClient) -> None:
    body = await _signup(api)

    assert body["tenant_slug"] == "northwind-freight"
    assert body["role"] == "admin"
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0

    me = await api.get("/api/v1/auth/me", headers=_auth(body["access_token"]))

    assert me.status_code == 200
    assert me.json()["email"] == SIGNUP["email"]
    assert "password_hash" not in me.json()


async def test_signup_rejects_a_slug_already_in_use(api: AsyncClient) -> None:
    await _signup(api)
    again = await api.post("/api/v1/auth/signup", json=SIGNUP)

    assert again.status_code == 409
    assert again.json()["code"] == "conflict"


async def test_signup_rejects_a_malformed_slug(api: AsyncClient) -> None:
    response = await api.post("/api/v1/auth/signup", json={**SIGNUP, "tenant_slug": "Not A Slug"})

    assert response.status_code == 422


async def test_login_returns_a_token_and_sets_the_refresh_cookie(
    api: AsyncClient, clean_rate_limits: None
) -> None:
    await _signup(api)

    response = await api.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": SIGNUP["tenant_slug"],
            "email": SIGNUP["email"],
            "password": SIGNUP["password"],
        },
    )

    assert response.status_code == 200
    cookie = response.cookies.get("refresh_token")
    assert cookie
    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie
    assert "Path=/api/v1/auth" in set_cookie


async def test_wrong_password_and_unknown_email_answer_identically(
    api: AsyncClient, clean_rate_limits: None
) -> None:
    await _signup(api)

    wrong_password = await api.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": SIGNUP["tenant_slug"],
            "email": SIGNUP["email"],
            "password": "not the password",
        },
    )
    unknown_email = await api.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": SIGNUP["tenant_slug"],
            "email": "nobody@northwind.test",
            "password": "not the password",
        },
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


async def test_refresh_rotates_the_token(api: AsyncClient) -> None:
    await _signup(api)
    first = api.cookies.get("refresh_token")

    response = await api.post(REFRESH_PATH)

    assert response.status_code == 200
    second = response.cookies.get("refresh_token")
    assert second and second != first


async def test_reusing_a_rotated_token_kills_the_whole_family(api: AsyncClient) -> None:
    """A revoked token showing up again means it leaked, so every sibling dies."""
    await _signup(api)
    stolen = api.cookies.get("refresh_token")

    rotated = await api.post(REFRESH_PATH)
    assert rotated.status_code == 200
    current = api.cookies.get("refresh_token")

    api.cookies.set("refresh_token", stolen or "")
    replay = await api.post(REFRESH_PATH)
    assert replay.status_code == 401

    # The honest holder's token is gone too, which is the intended trade.
    api.cookies.set("refresh_token", current or "")
    after = await api.post(REFRESH_PATH)
    assert after.status_code == 401


async def test_refresh_without_a_cookie_is_rejected(api: AsyncClient) -> None:
    response = await api.post(REFRESH_PATH)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


async def test_logout_revokes_the_refresh_token(api: AsyncClient) -> None:
    await _signup(api)
    token = api.cookies.get("refresh_token")

    logout = await api.post("/api/v1/auth/logout")
    assert logout.status_code == 204

    api.cookies.set("refresh_token", token or "")
    after = await api.post(REFRESH_PATH)
    assert after.status_code == 401


async def test_access_token_is_required_for_me(api: AsyncClient) -> None:
    response = await api.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


async def test_refresh_token_is_not_accepted_as_a_bearer(api: AsyncClient) -> None:
    await _signup(api)
    refresh_cookie = api.cookies.get("refresh_token") or ""

    response = await api.get("/api/v1/auth/me", headers=_auth(refresh_cookie))

    assert response.status_code == 401


async def test_login_is_rate_limited(api: AsyncClient, clean_rate_limits: None) -> None:
    await _signup(api)
    payload = {
        "tenant_slug": SIGNUP["tenant_slug"],
        "email": SIGNUP["email"],
        "password": "wrong every time",
    }

    codes = [(await api.post("/api/v1/auth/login", json=payload)).status_code for _ in range(6)]

    assert codes[:5] == [401] * 5
    assert codes[5] == 429
