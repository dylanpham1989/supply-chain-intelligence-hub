"""The wiring that makes row-level security actually apply to a request.

get_current_user reads the tenant off the verified token and sets it on the
session. If that session is not the one the route handler queries with, the
context lands on a connection nobody uses and every policy silently sees no
tenant. These tests check the wiring, not the policies.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import current_tenant_id
from app.models import Tenant

pytestmark = pytest.mark.integration

ALPHA = {
    "company_name": "Alpha Freight",
    "tenant_slug": "alpha-freight",
    "email": "admin@alpha.test",
    "password": "alpha password 1",
    "full_name": "Alpha Admin",
}
BETA = {
    "company_name": "Beta Freight",
    "tenant_slug": "beta-freight",
    "email": "admin@beta.test",
    "password": "beta password 11",
    "full_name": "Beta Admin",
}


async def _signup(api: AsyncClient, payload: dict) -> str:
    response = await api.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_a_request_sets_the_tenant_context_on_the_session_it_queries_with(
    api: AsyncClient, session: AsyncSession
) -> None:
    token = await _signup(api, ALPHA)
    assert await current_tenant_id(session) is not None

    response = await api.get("/api/v1/auth/me", headers=_auth(token))
    assert response.status_code == 200

    tenant = (
        await session.execute(Tenant.__table__.select().where(Tenant.slug == ALPHA["tenant_slug"]))
    ).one()

    assert await current_tenant_id(session) == tenant.id


async def test_each_token_scopes_its_own_request(api: AsyncClient) -> None:
    alpha_token = await _signup(api, ALPHA)
    beta_token = await _signup(api, BETA)

    alpha_me = await api.get("/api/v1/auth/me", headers=_auth(alpha_token))
    beta_me = await api.get("/api/v1/auth/me", headers=_auth(beta_token))

    assert alpha_me.json()["email"] == ALPHA["email"]
    assert beta_me.json()["email"] == BETA["email"]


async def test_one_tenant_cannot_read_another_tenants_user_by_id(api: AsyncClient) -> None:
    alpha_token = await _signup(api, ALPHA)
    beta_token = await _signup(api, BETA)

    beta_user_id = (await api.get("/api/v1/auth/me", headers=_auth(beta_token))).json()["id"]
    response = await api.get(f"/api/v1/users/{beta_user_id}", headers=_auth(alpha_token))

    # 404 and not 403: a 403 would confirm the id exists somewhere.
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_a_tenant_only_lists_its_own_users(api: AsyncClient) -> None:
    alpha_token = await _signup(api, ALPHA)
    await _signup(api, BETA)

    response = await api.get("/api/v1/users", headers=_auth(alpha_token))

    assert response.status_code == 200
    emails = [u["email"] for u in response.json()["items"]]
    assert emails == [ALPHA["email"]]


async def test_a_token_for_a_deleted_tenant_is_rejected(
    api: AsyncClient, session: AsyncSession
) -> None:
    token = await _signup(api, ALPHA)
    await session.execute(Tenant.__table__.delete().where(Tenant.slug == ALPHA["tenant_slug"]))
    await session.flush()

    response = await api.get("/api/v1/auth/me", headers=_auth(token))

    assert response.status_code == 401


SPOOF_HEADERS = [
    "X-Tenant-Id",
    "X-Tenant-Slug",
    "Tenant-Id",
    "X-Tenant",
]


@pytest.mark.parametrize("header", SPOOF_HEADERS)
async def test_a_header_cannot_choose_the_tenant(api: AsyncClient, header: str) -> None:
    """The tenant must come from the signed token and nowhere else.

    This is the mistake that costs the most: reading the tenant off anything the
    caller controls makes every policy underneath decorative. Nothing here fails
    at import or at request time, so it needs its own test.
    """
    alpha_token = await _signup(api, ALPHA)
    beta_token = await _signup(api, BETA)
    beta = (await api.get("/api/v1/auth/me", headers=_auth(beta_token))).json()

    response = await api.get(
        "/api/v1/auth/me",
        headers={**_auth(alpha_token), header: str(beta["id"])},
    )

    assert response.status_code == 200
    assert response.json()["email"] == ALPHA["email"], (
        f"{header} changed which tenant the request ran as"
    )


async def test_a_query_parameter_cannot_choose_the_tenant(api: AsyncClient) -> None:
    alpha_token = await _signup(api, ALPHA)
    beta_token = await _signup(api, BETA)
    beta = (await api.get("/api/v1/auth/me", headers=_auth(beta_token))).json()

    response = await api.get(
        "/api/v1/users",
        params={"tenant_id": beta["id"], "tenant_slug": BETA["tenant_slug"]},
        headers=_auth(alpha_token),
    )

    assert response.status_code == 200
    assert [u["email"] for u in response.json()["items"]] == [ALPHA["email"]]


async def test_a_request_body_cannot_choose_the_tenant(api: AsyncClient) -> None:
    alpha_token = await _signup(api, ALPHA)
    beta_token = await _signup(api, BETA)
    beta = (await api.get("/api/v1/auth/me", headers=_auth(beta_token))).json()

    created = await api.post(
        "/api/v1/users",
        json={
            "email": "planted@alpha.test",
            "password": "a long enough password",
            "full_name": "Planted User",
            "role": "viewer",
            "tenant_id": beta["id"],
        },
        headers=_auth(alpha_token),
    )

    # extra="forbid" on the schema turns this away before it reaches the service.
    assert created.status_code == 422

    listing = await api.get("/api/v1/users", headers=_auth(beta_token))
    assert "planted@alpha.test" not in [u["email"] for u in listing.json()["items"]]
