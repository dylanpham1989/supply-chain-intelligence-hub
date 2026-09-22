from httpx import AsyncClient


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
