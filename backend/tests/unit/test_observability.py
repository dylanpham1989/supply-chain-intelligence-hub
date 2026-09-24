from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core import metrics
from app.core.logging import REDACTED, redact_sensitive
from app.middleware.request_context import REQUEST_ID_HEADER


async def test_request_id_is_echoed_back(client: AsyncClient) -> None:
    response = await client.get("/health/live", headers={REQUEST_ID_HEADER: "trace-123"})

    assert response.headers[REQUEST_ID_HEADER] == "trace-123"


async def test_request_id_is_generated_when_absent(client: AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.headers[REQUEST_ID_HEADER]


async def test_unsafe_request_id_is_replaced(client: AsyncClient) -> None:
    """A caller-supplied id lands in the logs, so a forged one is discarded.

    Without this, a newline in the header lets a caller write log lines of their
    own choosing into the aggregator.
    """
    response = await client.get("/health/live", headers={REQUEST_ID_HEADER: "a b\nfake event"})

    assert response.headers[REQUEST_ID_HEADER] != "a b\nfake event"


async def test_liveness_does_not_touch_the_database(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Liveness failing restarts the pod, so a slow database must not fail it.

    If it did, one unhealthy database would restart every pod at once and the
    reconnect storm would keep it unhealthy.
    """

    async def explode(_: object) -> None:
        raise AssertionError("liveness probed a dependency")

    monkeypatch.setattr("app.api.health._ping_db", explode)
    monkeypatch.setattr("app.api.health._ping_redis", explode)
    monkeypatch.setattr("app.api.health._ping_s3", explode)

    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_reports_each_dependency(client: AsyncClient) -> None:
    response = await client.get("/health/ready")

    body = response.json()
    assert set(body) == {"status", "db", "redis", "s3"}
    assert response.status_code == (200 if body["status"] == "ok" else 503)


async def test_readiness_degrades_when_a_dependency_is_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def explode(_: object) -> None:
        raise ConnectionError("redis is gone")

    monkeypatch.setattr("app.api.health._ping_redis", explode)

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["redis"] is False


async def test_info_reports_the_build(client: AsyncClient) -> None:
    body = (await client.get("/health/info")).json()

    assert set(body) == {"version", "git_sha", "built_at", "env"}


async def test_metrics_label_the_route_template_not_the_url(client: AsyncClient) -> None:
    """A path with an id in it would mint one time series per shipment."""
    shipment_id = uuid4()
    await client.get(f"/api/v1/shipments/{shipment_id}")

    body = (await client.get("/metrics")).text

    assert 'route="/api/v1/shipments/{shipment_id}"' in body
    assert str(shipment_id) not in body


async def test_unmatched_paths_share_one_label(client: AsyncClient) -> None:
    """Otherwise anyone on the internet can add series by guessing urls."""
    await client.get("/does-not-exist-" + uuid4().hex)

    body = (await client.get("/metrics")).text

    assert 'route="unmatched"' in body


async def test_latency_histogram_uses_custom_buckets(client: AsyncClient) -> None:
    await client.get("/health/live")

    body = (await client.get("/metrics")).text

    # The prometheus default stops at 10s, which puts every llm call in +Inf.
    assert 'http_request_duration_seconds_bucket{le="2.5"' in body


def test_tenant_label_is_capped() -> None:
    metrics._tracked_tenants.clear()
    labels = {metrics.tenant_label(uuid4()) for _ in range(metrics.MAX_TENANT_LABELS + 10)}

    assert len(labels) == metrics.MAX_TENANT_LABELS + 1
    assert metrics.OTHER_TENANT in labels


def test_credentials_are_redacted_before_rendering() -> None:
    event = redact_sensitive(
        None,
        "info",
        {"event": "auth.login", "authorization": "Bearer abc", "api_key": "sk-1", "user": "a"},
    )

    assert event["authorization"] == REDACTED
    assert event["api_key"] == REDACTED
    assert event["user"] == "a"
