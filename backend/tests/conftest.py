from collections.abc import AsyncIterator

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    # ASGITransport does not run lifespan, and /health needs what it sets up.
    app = create_app()
    transport = ASGITransport(app=app)
    async with (
        LifespanManager(app),
        AsyncClient(transport=transport, base_url="http://testserver") as ac,
    ):
        yield ac
