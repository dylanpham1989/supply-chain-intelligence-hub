"""Redis is outside the database, so row-level security cannot help here.

If a cache key omits the tenant, one customer is served another customer's
dashboard and nothing downstream notices. These tests go through the real redis
the app uses.
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis

from app.core.config import settings

pytestmark = pytest.mark.integration

ALPHA = {
    "company_name": "Cache Alpha",
    "tenant_slug": "cache-alpha",
    "email": "admin@cache-alpha.test",
    "password": "alpha password 1",
    "full_name": "Alpha Admin",
}
BETA = {
    "company_name": "Cache Beta",
    "tenant_slug": "cache-beta",
    "email": "admin@cache-beta.test",
    "password": "beta password 11",
    "full_name": "Beta Admin",
}


@pytest.fixture
async def redis_client():
    client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    async for key in client.scan_iter("t:*"):
        await client.delete(key)
    yield client
    async for key in client.scan_iter("t:*"):
        await client.delete(key)
    await client.aclose()


async def _signup(api: AsyncClient, payload: dict) -> str:
    response = await api.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _shipment(reference: str, **over: object) -> dict:
    return {
        "reference": reference,
        "origin_country": "CN",
        "dest_country": "DE",
        "mode": "ocean",
        "qty": 10,
        "value_usd": "1000.00",
        "eta": str(date(2026, 6, 1)),
        "status": "planned",
        **over,
    }


async def test_two_tenants_do_not_share_a_cached_summary(
    api: AsyncClient, redis_client: Redis
) -> None:
    alpha = await _signup(api, ALPHA)
    beta = await _signup(api, BETA)

    for i in range(3):
        assert (
            await api.post("/api/v1/shipments", json=_shipment(f"A-{i}"), headers=_auth(alpha))
        ).status_code == 201
    assert (
        await api.post("/api/v1/shipments", json=_shipment("B-0"), headers=_auth(beta))
    ).status_code == 201

    alpha_summary = await api.get("/api/v1/analytics/summary", headers=_auth(alpha))
    beta_summary = await api.get("/api/v1/analytics/summary", headers=_auth(beta))

    assert alpha_summary.json()["total_shipments"] == 3
    assert beta_summary.json()["total_shipments"] == 1


async def test_every_cache_key_is_namespaced_by_tenant(
    api: AsyncClient, redis_client: Redis
) -> None:
    alpha = await _signup(api, ALPHA)
    beta = await _signup(api, BETA)
    await api.get("/api/v1/analytics/summary", headers=_auth(alpha))
    await api.get("/api/v1/analytics/summary", headers=_auth(beta))

    keys = [k async for k in redis_client.scan_iter("*analytics:summary*")]

    assert len(keys) == 2, keys
    assert all(k.startswith("t:") for k in keys)
    assert len({k.split(":")[1] for k in keys}) == 2, "both tenants share one key"


async def test_the_second_read_is_served_from_cache(api: AsyncClient, redis_client: Redis) -> None:
    alpha = await _signup(api, ALPHA)

    first = await api.get("/api/v1/analytics/summary", headers=_auth(alpha))
    second = await api.get("/api/v1/analytics/summary", headers=_auth(alpha))

    assert first.headers["X-Cache"] == "miss"
    assert second.headers["X-Cache"] == "hit"
    assert first.json() == second.json()


async def test_writing_a_shipment_invalidates_the_dashboard(
    api: AsyncClient, redis_client: Redis
) -> None:
    """A stale dashboard after the user just added a row reads as a bug."""
    alpha = await _signup(api, ALPHA)
    await api.post("/api/v1/shipments", json=_shipment("INV-1"), headers=_auth(alpha))

    warmed = await api.get("/api/v1/analytics/summary", headers=_auth(alpha))
    assert warmed.json()["total_shipments"] == 1
    assert (await api.get("/api/v1/analytics/summary", headers=_auth(alpha))).headers[
        "X-Cache"
    ] == "hit"

    await api.post("/api/v1/shipments", json=_shipment("INV-2"), headers=_auth(alpha))
    after = await api.get("/api/v1/analytics/summary", headers=_auth(alpha))

    assert after.headers["X-Cache"] == "miss"
    assert after.json()["total_shipments"] == 2


async def test_one_tenants_write_does_not_flush_another_tenants_cache(
    api: AsyncClient, redis_client: Redis
) -> None:
    alpha = await _signup(api, ALPHA)
    beta = await _signup(api, BETA)
    await api.get("/api/v1/analytics/summary", headers=_auth(beta))

    await api.post("/api/v1/shipments", json=_shipment("A-1"), headers=_auth(alpha))
    beta_again = await api.get("/api/v1/analytics/summary", headers=_auth(beta))

    assert beta_again.headers["X-Cache"] == "hit"


async def test_different_windows_are_cached_separately(
    api: AsyncClient, redis_client: Redis
) -> None:
    alpha = await _signup(api, ALPHA)
    old = str(date.today() - timedelta(days=200))
    await api.post("/api/v1/shipments", json=_shipment("W-1", eta=old), headers=_auth(alpha))

    year = await api.get("/api/v1/analytics/summary?days=365", headers=_auth(alpha))
    week = await api.get("/api/v1/analytics/summary?days=7", headers=_auth(alpha))

    assert year.headers["X-Cache"] == "miss"
    assert week.headers["X-Cache"] == "miss", "window must be part of the key"


async def test_the_api_still_answers_when_redis_is_unreachable(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail open. A cache outage should be slow, not fatal."""
    from redis.exceptions import ConnectionError as RedisConnectionError

    async def explode(*args: object, **kwargs: object) -> None:
        raise RedisConnectionError("redis is down")

    alpha = await _signup(api, ALPHA)
    monkeypatch.setattr(Redis, "get", explode)
    monkeypatch.setattr(Redis, "execute_command", explode)

    response = await api.get("/api/v1/analytics/summary", headers=_auth(alpha))

    assert response.status_code == 200
    assert response.headers["X-Cache"] == "miss"
