"""Every analytics endpoint, against real rows.

These are raw SQL, so a broken cast or a bad bind parameter only shows up when
the statement actually runs.
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

OWNER = {
    "company_name": "Metrics Freight",
    "tenant_slug": "metrics-freight",
    "email": "admin@metrics.test",
    "password": "metrics password",
    "full_name": "Metrics Admin",
}

ENDPOINTS = [
    "/api/v1/analytics/summary",
    "/api/v1/analytics/shipments-by-status",
    "/api/v1/analytics/shipments-timeseries",
    "/api/v1/analytics/top-suppliers",
    "/api/v1/analytics/risk-breakdown",
]


async def _token(api: AsyncClient) -> str:
    response = await api.post("/api/v1/auth/signup", json=OWNER)
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _add_shipment(api: AsyncClient, token: str, ref: str, **over: object) -> None:
    payload = {
        "reference": ref,
        "origin_country": "CN",
        "dest_country": "DE",
        "mode": "ocean",
        "qty": 5,
        "value_usd": "2500.00",
        "eta": str(date.today() - timedelta(days=10)),
        "status": "delivered",
        "ata": str(date.today() - timedelta(days=11)),
        **over,
    }
    response = await api.post("/api/v1/shipments", json=payload, headers=_auth(token))
    assert response.status_code == 201, response.text


@pytest.mark.parametrize("endpoint", ENDPOINTS)
async def test_endpoint_answers_on_an_empty_workspace(api: AsyncClient, endpoint: str) -> None:
    token = await _token(api)

    response = await api.get(endpoint, headers=_auth(token))

    assert response.status_code == 200, response.text


@pytest.mark.parametrize("endpoint", ENDPOINTS)
async def test_endpoint_answers_with_rows(api: AsyncClient, endpoint: str) -> None:
    token = await _token(api)
    await _add_shipment(api, token, "AN-1")
    await _add_shipment(
        api, token, "AN-2", status="delayed", ata=str(date.today() - timedelta(days=3))
    )

    response = await api.get(endpoint, headers=_auth(token))

    assert response.status_code == 200, response.text


async def test_summary_counts_match_the_rows(api: AsyncClient) -> None:
    token = await _token(api)
    await _add_shipment(api, token, "SUM-1")
    await _add_shipment(
        api, token, "SUM-2", status="delayed", ata=str(date.today() - timedelta(days=2))
    )

    body = (await api.get("/api/v1/analytics/summary", headers=_auth(token))).json()

    assert body["total_shipments"] == 2
    assert body["delayed"] == 1
    assert body["on_time_rate"] == 0.5
    assert body["avg_delay_days"] == 8.0


async def test_timeseries_fills_empty_months(api: AsyncClient) -> None:
    """generate_series is there so a quiet month is a zero, not a missing point."""
    token = await _token(api)
    await _add_shipment(api, token, "TS-1")

    items = (
        await api.get("/api/v1/analytics/shipments-timeseries?days=180", headers=_auth(token))
    ).json()["items"]

    assert len(items) >= 6, items
    assert any(point["shipments"] == 0 for point in items), "empty months were dropped"
    months = [point["month"] for point in items]
    assert months == sorted(months)


async def test_status_breakdown_sums_to_the_total(api: AsyncClient) -> None:
    token = await _token(api)
    for i in range(3):
        await _add_shipment(api, token, f"ST-{i}")

    breakdown = (
        await api.get("/api/v1/analytics/shipments-by-status", headers=_auth(token))
    ).json()

    assert sum(item["shipments"] for item in breakdown["items"]) == 3


async def test_top_suppliers_ignores_suppliers_with_no_shipments(api: AsyncClient) -> None:
    token = await _token(api)
    created = await api.post(
        "/api/v1/suppliers",
        json={"name": "Idle Supplier", "country": "CN", "category": "electronics"},
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text

    items = (await api.get("/api/v1/analytics/top-suppliers", headers=_auth(token))).json()["items"]

    assert items == []


async def test_window_is_bounded(api: AsyncClient) -> None:
    token = await _token(api)

    too_wide = await api.get("/api/v1/analytics/summary?days=100000", headers=_auth(token))

    assert too_wide.status_code == 422
