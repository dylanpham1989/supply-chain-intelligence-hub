from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.deps import get_session
from app.db.rls import set_tenant_context
from app.main import create_app
from app.models import Tenant

TenantSwitch = Callable[[UUID], Awaitable[None]]

# The first run loads the embedding model, which is slower than the default.
STARTUP_TIMEOUT_S = 120.0

UNREACHABLE = (
    "cannot reach postgres at {url}. run `make up` first, or point DATABASE_URL at a "
    "migrated database."
)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Connects as app_user, the role the application uses and RLS applies to."""
    eng = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await eng.dispose()
        pytest.fail(UNREACHABLE.format(url=settings.database_url) + f"\n{exc}")
    yield eng
    await eng.dispose()


@pytest.fixture
async def conn(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    connection = await engine.connect()
    transaction = await connection.begin()
    yield connection
    await transaction.rollback()
    await connection.close()


@pytest.fixture
async def session(conn: AsyncConnection) -> AsyncIterator[AsyncSession]:
    """Everything a test writes is rolled back, so tests can run against a seeded db.

    create_savepoint is needed because code under test calls commit(); without it
    the commit would end the outer transaction and the rollback would find nothing.
    """
    async with AsyncSession(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    ) as s:
        yield s


async def _make_tenant(session: AsyncSession, slug: str) -> Tenant:
    tenant = Tenant(slug=slug, name=slug.replace("-", " ").title())
    session.add(tenant)
    await session.flush()
    return tenant


@pytest.fixture
async def tenant_a(session: AsyncSession) -> Tenant:
    return await _make_tenant(session, "rls-tenant-a")


@pytest.fixture
async def tenant_b(session: AsyncSession) -> Tenant:
    return await _make_tenant(session, "rls-tenant-b")


@pytest.fixture
async def as_tenant(session: AsyncSession) -> TenantSwitch:
    async def _switch(tenant_id: UUID) -> None:
        await set_tenant_context(session, tenant_id)

    return _switch


@pytest.fixture
async def api(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """App wired to the rolled-back test session.

    Overriding get_session is what lets a request and the test see the same
    transaction, and it is also how the tenant context set inside
    get_current_user stays observable from the test.
    """
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _session_override
    transport = ASGITransport(app=app)
    async with (
        LifespanManager(app, startup_timeout=STARTUP_TIMEOUT_S),
        AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def clean_rate_limits() -> AsyncIterator[None]:
    """Rate limit state lives in the real redis, so it would leak between tests."""
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    async for key in redis.scan_iter("rl:*"):
        await redis.delete(key)
    yield
    async for key in redis.scan_iter("rl:*"):
        await redis.delete(key)
    await redis.aclose()
