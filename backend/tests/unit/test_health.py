import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.main import create_app


async def test_health_reports_dependency_status(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code in (200, 503)
    body = response.json()
    assert set(body) == {"status", "db", "redis"}
    assert body["status"] in ("ok", "degraded")
    assert isinstance(body["db"], bool)
    assert isinstance(body["redis"], bool)


async def test_root_redirects_to_docs(client: AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


async def test_openapi_schema_is_served(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"]


def test_schema_is_exposed_in_local_env() -> None:
    app = create_app()

    assert app.openapi_url == "/openapi.json"
    assert app.docs_url == "/docs"


def test_schema_is_hidden_in_prod_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The schema describes the whole attack surface, so it stays off in prod."""
    monkeypatch.setattr(settings, "env", "prod")

    app = create_app()

    assert app.openapi_url is None
    assert app.docs_url is None
    assert not any(route.path == "/" for route in app.routes)
