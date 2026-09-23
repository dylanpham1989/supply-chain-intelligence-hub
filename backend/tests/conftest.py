from collections.abc import AsyncIterator

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.main import create_app

# The first run loads the embedding model, which is slower than the default.
STARTUP_TIMEOUT_S = 120.0


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    # ASGITransport does not run lifespan, and /health needs what it sets up.
    app = create_app()
    transport = ASGITransport(app=app)
    async with (
        LifespanManager(app, startup_timeout=STARTUP_TIMEOUT_S),
        AsyncClient(transport=transport, base_url="http://testserver") as ac,
    ):
        yield ac
