from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine

from app.core.config import settings
from app.db.rls import set_tenant_context
from app.models import Tenant

TenantSwitch = Callable[[UUID], Awaitable[None]]

UNREACHABLE = (
    "cannot reach postgres at {url}. run `make up` first, or point DATABASE_URL at a "
    "migrated database."
)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Connects as app_user, the role the application uses and RLS applies to."""
    eng = create_async_engine(settings.database_url, poolclass=None)
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
