"""Single-resource reads and writes, including what another tenant gets back."""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

ALPHA = {
    "company_name": "Crud Alpha",
    "tenant_slug": "crud-alpha",
    "email": "admin@crud-alpha.test",
    "password": "alpha password 1",
    "full_name": "Alpha Admin",
}
BETA = {
    "company_name": "Crud Beta",
    "tenant_slug": "crud-beta",
    "email": "admin@crud-beta.test",
    "password": "beta password 11",
    "full_name": "Beta Admin",
}


async def _token(api: AsyncClient, payload: dict) -> str:
    response = await api.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _shipment(api: AsyncClient, token: str, ref: str = "CR-1") -> dict:
    response = await api.post(
        "/api/v1/shipments",
        json={
            "reference": ref,
            "origin_country": "cn",
            "dest_country": "de",
            "mode": "ocean",
            "qty": 3,
            "value_usd": "750.00",
            "eta": str(date.today() + timedelta(days=5)),
            "status": "planned",
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_country_codes_are_stored_upper_case(api: AsyncClient) -> None:
    token = await _token(api, ALPHA)

    created = await _shipment(api, token)

    assert created["origin_country"] == "CN"
    assert created["dest_country"] == "DE"


async def test_get_update_and_delete_a_shipment(api: AsyncClient) -> None:
    token = await _token(api, ALPHA)
    created = await _shipment(api, token)

    fetched = await api.get(f"/api/v1/shipments/{created['id']}", headers=_auth(token))
    assert fetched.status_code == 200
    assert fetched.json()["reference"] == "CR-1"

    updated = await api.patch(
        f"/api/v1/shipments/{created['id']}",
        json={"qty": 12, "status": "in_transit"},
        headers=_auth(token),
    )
    assert updated.status_code == 200
    assert updated.json()["qty"] == 12
    assert updated.json()["status"] == "in_transit"

    removed = await api.delete(f"/api/v1/shipments/{created['id']}", headers=_auth(token))
    assert removed.status_code == 204

    gone = await api.get(f"/api/v1/shipments/{created['id']}", headers=_auth(token))
    assert gone.status_code == 404


async def test_updating_to_delayed_raises_an_alert(api: AsyncClient) -> None:
    token = await _token(api, ALPHA)
    created = await _shipment(api, token)

    await api.patch(
        f"/api/v1/shipments/{created['id']}",
        json={"status": "delayed", "ata": str(date.today() + timedelta(days=15))},
        headers=_auth(token),
    )
    alerts = (await api.get("/api/v1/alerts", headers=_auth(token))).json()

    assert any("CR-1" in a["title"] for a in alerts["items"])


async def test_another_tenant_gets_404_not_403(api: AsyncClient) -> None:
    alpha = await _token(api, ALPHA)
    beta = await _token(api, BETA)
    created = await _shipment(api, alpha)

    for method in ("get", "delete"):
        response = await getattr(api, method)(
            f"/api/v1/shipments/{created['id']}", headers=_auth(beta)
        )
        assert response.status_code == 404, method

    patched = await api.patch(
        f"/api/v1/shipments/{created['id']}", json={"qty": 1}, headers=_auth(beta)
    )
    assert patched.status_code == 404


async def test_supplier_create_get_and_performance(api: AsyncClient) -> None:
    token = await _token(api, ALPHA)

    created = await api.post(
        "/api/v1/suppliers",
        json={"name": "Perf Supplier", "country": "vn", "category": "textiles"},
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text
    supplier = created.json()
    assert supplier["country"] == "VN"

    await api.post(
        "/api/v1/shipments",
        json={
            "reference": "PERF-1",
            "supplier_id": supplier["id"],
            "origin_country": "VN",
            "dest_country": "NL",
            "mode": "air",
            "qty": 1,
            "value_usd": "100.00",
            "eta": str(date.today() - timedelta(days=5)),
            "ata": str(date.today() - timedelta(days=1)),
            "status": "delayed",
        },
        headers=_auth(token),
    )

    fetched = await api.get(f"/api/v1/suppliers/{supplier['id']}", headers=_auth(token))
    assert fetched.status_code == 200

    performance = await api.get(
        f"/api/v1/suppliers/{supplier['id']}/performance", headers=_auth(token)
    )
    assert performance.status_code == 200
    body = performance.json()
    assert body["shipments"] == 1
    assert body["late"] == 1
    assert body["on_time_rate"] == 0.0
    assert body["monthly"]


async def test_duplicate_supplier_name_is_a_conflict(api: AsyncClient) -> None:
    token = await _token(api, ALPHA)
    payload = {"name": "Only Once", "country": "CN", "category": "metals"}

    assert (
        await api.post("/api/v1/suppliers", json=payload, headers=_auth(token))
    ).status_code == 201
    assert (
        await api.post("/api/v1/suppliers", json=payload, headers=_auth(token))
    ).status_code == 409


async def test_two_tenants_may_use_the_same_supplier_name(api: AsyncClient) -> None:
    """Uniqueness is per tenant; two customers can both buy from the same vendor."""
    alpha = await _token(api, ALPHA)
    beta = await _token(api, BETA)
    payload = {"name": "Shared Vendor", "country": "CN", "category": "metals"}

    assert (
        await api.post("/api/v1/suppliers", json=payload, headers=_auth(alpha))
    ).status_code == 201
    assert (
        await api.post("/api/v1/suppliers", json=payload, headers=_auth(beta))
    ).status_code == 201


async def test_marking_one_alert_read(api: AsyncClient) -> None:
    token = await _token(api, ALPHA)
    created = await _shipment(api, token)
    await api.patch(
        f"/api/v1/shipments/{created['id']}",
        json={"status": "delayed", "ata": str(date.today() + timedelta(days=9))},
        headers=_auth(token),
    )
    alert = (await api.get("/api/v1/alerts", headers=_auth(token))).json()["items"][0]

    marked = await api.patch(f"/api/v1/alerts/{alert['id']}/read", headers=_auth(token))

    assert marked.status_code == 200
    assert marked.json()["is_read"] is True
