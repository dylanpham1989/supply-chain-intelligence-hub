"""Role enforcement at the endpoint, not in the UI.

The frontend hides what a role cannot do, but that is presentation. These go
straight at the API with each role's token.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

OWNER = {
    "company_name": "Rbac Freight",
    "tenant_slug": "rbac-freight",
    "email": "admin@rbac.test",
    "password": "admin password 1",
    "full_name": "Rbac Admin",
}
PASSWORD = "member password 1"


async def _workspace(api: AsyncClient) -> dict[str, str]:
    """One workspace with an admin, an analyst and a viewer, keyed by role."""
    signup = await api.post("/api/v1/auth/signup", json=OWNER)
    assert signup.status_code == 201, signup.text
    admin_token = signup.json()["access_token"]

    tokens = {"admin": admin_token}
    for role in ("analyst", "viewer"):
        created = await api.post(
            "/api/v1/users",
            json={
                "email": f"{role}@rbac.test",
                "password": PASSWORD,
                "full_name": f"Rbac {role.title()}",
                "role": role,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert created.status_code == 201, created.text

        login = await api.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": OWNER["tenant_slug"],
                "email": f"{role}@rbac.test",
                "password": PASSWORD,
            },
        )
        assert login.status_code == 200, login.text
        tokens[role] = login.json()["access_token"]
    return tokens


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    ("role", "expected"),
    [("admin", 200), ("analyst", 200), ("viewer", 403)],
)
async def test_listing_users_needs_user_read(
    api: AsyncClient, clean_rate_limits: None, role: str, expected: int
) -> None:
    tokens = await _workspace(api)

    response = await api.get("/api/v1/users", headers=_auth(tokens[role]))

    assert response.status_code == expected


@pytest.mark.parametrize(
    ("role", "expected"),
    [("admin", 201), ("analyst", 403), ("viewer", 403)],
)
async def test_creating_a_user_needs_user_write(
    api: AsyncClient, clean_rate_limits: None, role: str, expected: int
) -> None:
    tokens = await _workspace(api)

    response = await api.post(
        "/api/v1/users",
        json={
            "email": f"new-by-{role}@rbac.test",
            "password": "another long password",
            "full_name": "New User",
            "role": "viewer",
        },
        headers=_auth(tokens[role]),
    )

    assert response.status_code == expected


@pytest.mark.parametrize(
    ("role", "expected"),
    [("admin", 204), ("analyst", 403), ("viewer", 403)],
)
async def test_deactivating_a_user_needs_user_write(
    api: AsyncClient, clean_rate_limits: None, role: str, expected: int
) -> None:
    tokens = await _workspace(api)
    target = (await api.get("/api/v1/auth/me", headers=_auth(tokens["viewer"]))).json()

    response = await api.delete(f"/api/v1/users/{target['id']}", headers=_auth(tokens[role]))

    assert response.status_code == expected


async def test_a_forbidden_response_names_the_missing_permission(
    api: AsyncClient, clean_rate_limits: None
) -> None:
    tokens = await _workspace(api)

    response = await api.get("/api/v1/users", headers=_auth(tokens["viewer"]))

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    assert "user:read" in response.json()["message"]


async def test_every_role_can_read_its_own_profile(
    api: AsyncClient, clean_rate_limits: None
) -> None:
    tokens = await _workspace(api)

    for role, token in tokens.items():
        response = await api.get("/api/v1/auth/me", headers=_auth(token))

        assert response.status_code == 200, role
        assert response.json()["role"] == role


async def test_an_admin_cannot_demote_the_last_admin(
    api: AsyncClient, clean_rate_limits: None
) -> None:
    tokens = await _workspace(api)
    me = (await api.get("/api/v1/auth/me", headers=_auth(tokens["admin"]))).json()

    response = await api.patch(
        f"/api/v1/users/{me['id']}", json={"role": "viewer"}, headers=_auth(tokens["admin"])
    )

    assert response.status_code == 403
    assert "role" in response.json()["message"]


async def test_an_admin_cannot_deactivate_itself(api: AsyncClient, clean_rate_limits: None) -> None:
    tokens = await _workspace(api)
    me = (await api.get("/api/v1/auth/me", headers=_auth(tokens["admin"]))).json()

    response = await api.delete(f"/api/v1/users/{me['id']}", headers=_auth(tokens["admin"]))

    assert response.status_code == 403


async def test_a_deactivated_user_loses_access(api: AsyncClient, clean_rate_limits: None) -> None:
    tokens = await _workspace(api)
    viewer = (await api.get("/api/v1/auth/me", headers=_auth(tokens["viewer"]))).json()

    deactivated = await api.delete(f"/api/v1/users/{viewer['id']}", headers=_auth(tokens["admin"]))
    assert deactivated.status_code == 204

    # The access token is still valid and unexpired; the user lookup is what stops it.
    response = await api.get("/api/v1/auth/me", headers=_auth(tokens["viewer"]))

    assert response.status_code == 401
