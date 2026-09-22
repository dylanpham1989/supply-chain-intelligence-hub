"""Shipment listing: filters, sorting, paging, and what a caller may not ask for."""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

OWNER = {
    "company_name": "List Freight",
    "tenant_slug": "list-freight",
    "email": "admin@list.test",
    "password": "listing password",
    "full_name": "List Admin",
}


async def _token(api: AsyncClient) -> str:
    response = await api.post("/api/v1/auth/signup", json=OWNER)
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed(api: AsyncClient, token: str) -> None:
    rows = [
        ("LF-001", "planned", "CN", "DE", "ocean", "1000.00", 30),
        ("LF-002", "delayed", "VN", "NL", "air", "5000.00", 20),
        ("LF-003", "delivered", "CN", "FR", "ocean", "2500.00", 10),
        ("LF-004", "in_transit", "JP", "US", "rail", "9000.00", 5),
    ]
    for ref, status, origin, dest, mode, value, days_ago in rows:
        payload = {
            "reference": ref,
            "origin_country": origin,
            "dest_country": dest,
            "mode": mode,
            "qty": 1,
            "value_usd": value,
            "eta": str(date.today() - timedelta(days=days_ago)),
            "status": status,
        }
        if status in ("delivered", "delayed"):
            offset = days_ago - 4 if status == "delayed" else days_ago + 1
            payload["ata"] = str(date.today() - timedelta(days=offset))
        created = await api.post("/api/v1/shipments", json=payload, headers=_auth(token))
        assert created.status_code == 201, created.text


async def test_listing_returns_the_page_envelope(api: AsyncClient) -> None:
    token = await _token(api)
    await _seed(api, token)

    body = (await api.get("/api/v1/shipments", headers=_auth(token))).json()

    assert set(body) == {"items", "total", "page", "size", "pages"}
    assert body["total"] == 4
    assert body["pages"] == 1


async def test_filter_by_status(api: AsyncClient) -> None:
    token = await _token(api)
    await _seed(api, token)

    body = (await api.get("/api/v1/shipments?status=delayed", headers=_auth(token))).json()

    assert body["total"] == 1
    assert body["items"][0]["reference"] == "LF-002"


async def test_filters_combine(api: AsyncClient) -> None:
    token = await _token(api)
    await _seed(api, token)

    body = (
        await api.get("/api/v1/shipments?origin_country=CN&mode=ocean", headers=_auth(token))
    ).json()

    assert {item["reference"] for item in body["items"]} == {"LF-001", "LF-003"}


async def test_late_only_uses_arrival_against_estimate(api: AsyncClient) -> None:
    token = await _token(api)
    await _seed(api, token)

    body = (await api.get("/api/v1/shipments?late_only=true", headers=_auth(token))).json()

    assert body["total"] == 1
    assert body["items"][0]["reference"] == "LF-002"
    assert body["items"][0]["delay_days"] > 0


async def test_search_matches_the_reference(api: AsyncClient) -> None:
    token = await _token(api)
    await _seed(api, token)

    body = (await api.get("/api/v1/shipments?search=LF-00", headers=_auth(token))).json()

    assert body["total"] == 4


async def test_sorting_and_paging_do_not_repeat_rows(api: AsyncClient) -> None:
    token = await _token(api)
    await _seed(api, token)

    first = (
        await api.get(
            "/api/v1/shipments?sort=value_usd&order=asc&size=2&page=1", headers=_auth(token)
        )
    ).json()
    second = (
        await api.get(
            "/api/v1/shipments?sort=value_usd&order=asc&size=2&page=2", headers=_auth(token)
        )
    ).json()

    assert [item["reference"] for item in first["items"]] == ["LF-001", "LF-003"]
    assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})
    assert first["pages"] == 2


async def test_sort_column_is_a_whitelist(api: AsyncClient) -> None:
    """A free-form sort column would let a caller order by, and read out, anything."""
    token = await _token(api)

    for column in ("password_hash", "tenant_id", "id; drop table shipments"):
        response = await api.get(f"/api/v1/shipments?sort={column}", headers=_auth(token))

        assert response.status_code == 422, column


async def test_page_size_is_capped(api: AsyncClient) -> None:
    token = await _token(api)

    response = await api.get("/api/v1/shipments?size=100000", headers=_auth(token))

    assert response.status_code == 422


async def test_unknown_filter_is_rejected(api: AsyncClient) -> None:
    token = await _token(api)

    response = await api.get("/api/v1/shipments?tenant_id=whatever", headers=_auth(token))

    assert response.status_code == 422


async def test_duplicate_reference_is_a_conflict(api: AsyncClient) -> None:
    token = await _token(api)
    await _seed(api, token)

    payload = {
        "reference": "LF-001",
        "origin_country": "CN",
        "dest_country": "DE",
        "mode": "ocean",
        "qty": 1,
        "value_usd": "1.00",
        "eta": str(date.today()),
        "status": "planned",
    }
    response = await api.post("/api/v1/shipments", json=payload, headers=_auth(token))

    assert response.status_code == 409


async def test_creating_a_delayed_shipment_raises_an_alert(api: AsyncClient) -> None:
    token = await _token(api)
    await _seed(api, token)

    alerts = (await api.get("/api/v1/alerts?unread_only=true", headers=_auth(token))).json()

    references = [a["title"] for a in alerts["items"]]
    assert any("LF-002" in title for title in references), references


async def test_alerts_can_be_marked_read(api: AsyncClient) -> None:
    token = await _token(api)
    await _seed(api, token)

    before = (await api.get("/api/v1/alerts/unread-count", headers=_auth(token))).json()
    assert before["unread"] >= 1

    await api.post("/api/v1/alerts/read-all", headers=_auth(token))
    after = (await api.get("/api/v1/alerts/unread-count", headers=_auth(token))).json()

    assert after["unread"] == 0
