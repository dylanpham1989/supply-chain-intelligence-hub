from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SET_TENANT = text("SELECT set_config('app.tenant_id', :tenant_id, true)")
_CURRENT_TENANT = text("SELECT current_setting('app.tenant_id', true)")


async def set_tenant_context(session: AsyncSession, tenant_id: UUID) -> None:
    """Scope every query on this transaction to one tenant.

    is_local=true is the whole point: the setting dies with the transaction, so a
    pooled connection cannot carry one tenant's id into the next request. SET LOCAL
    would do the same but takes no bind parameter, which means string interpolation.
    """
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})


async def current_tenant_id(session: AsyncSession) -> UUID | None:
    raw = (await session.execute(_CURRENT_TENANT)).scalar()
    return UUID(raw) if raw else None
