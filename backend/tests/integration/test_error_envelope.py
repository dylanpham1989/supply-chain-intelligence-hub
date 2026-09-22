"""Every failure answers in one shape.

FastAPI hands back three different bodies out of the box: our own, the
validation one, and the plain HTTPException one. A client should not have to
branch on which it got.
"""

import pytest
from httpx import AsyncClient, Response

pytestmark = pytest.mark.integration

REQUIRED_KEYS = {"code", "message"}


async def _assert_envelope(response: Response, expected_status: int, expected_code: str) -> None:
    assert response.status_code == expected_status, response.text
    body = response.json()
    assert set(body) >= REQUIRED_KEYS, body
    assert body["code"] == expected_code
    assert isinstance(body["message"], str)
    assert body["message"]


async def test_missing_token_uses_the_envelope(api: AsyncClient) -> None:
    await _assert_envelope(await api.get("/api/v1/users"), 401, "unauthenticated")


async def test_unknown_route_uses_the_envelope(api: AsyncClient) -> None:
    await _assert_envelope(await api.get("/api/v1/does-not-exist"), 404, "not_found")


async def test_wrong_method_uses_the_envelope(api: AsyncClient) -> None:
    await _assert_envelope(await api.delete("/api/v1/auth/login"), 405, "method_not_allowed")


async def test_validation_failure_uses_the_envelope_and_names_the_fields(
    api: AsyncClient,
) -> None:
    response = await api.post("/api/v1/auth/login", json={"tenant_slug": "x"})

    await _assert_envelope(response, 422, "validation_error")
    fields = {f["field"] for f in response.json()["fields"]}
    assert "tenant_slug" in fields
    assert "email" in fields


async def test_no_error_response_carries_a_traceback(api: AsyncClient) -> None:
    for response in (
        await api.get("/api/v1/users"),
        await api.get("/api/v1/does-not-exist"),
        await api.post("/api/v1/auth/login", json={}),
    ):
        text = response.text.lower()
        assert "traceback" not in text
        assert 'file "/' not in text
        assert "app/services" not in text
