from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import set_tenant_context
from app.db.session import SessionLocal


@asynccontextmanager
async def tenant_session(tenant_id: UUID) -> AsyncIterator[AsyncSession]:
    """The only way a job touches the database.

    A job has no request to carry the tenant, so it has to set the context
    itself. Forgetting it does not leak; the policies simply return nothing and
    the job fails in a way that is hard to read. Keeping it to one entry point
    is what stops that happening.
    """
    async with SessionLocal() as session:
        await set_tenant_context(session, tenant_id)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
