from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.types import TenantEntity


class TenantRepository[ModelT: TenantEntity]:
    """Base for anything reading tenant data.

    RLS already blocks cross-tenant rows at the database. Repeating the filter in
    the query keeps the planner on the tenant-leading indexes, and means a missing
    GUC shows up as an empty result rather than a leak. Taking tenant_id in the
    constructor makes "a repository with no tenant" impossible to write.
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def _scoped(self) -> Select[tuple[ModelT]]:
        return select(self.model).where(self.model.tenant_id == self.tenant_id)

    async def get(self, entity_id: UUID) -> ModelT | None:
        stmt = self._scoped().where(self.model.id == entity_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[ModelT]:
        stmt = self._scoped().limit(limit).offset(offset)
        return (await self.session.execute(stmt)).scalars().all()

    async def count(self) -> int:
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.tenant_id == self.tenant_id)
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def create(self, **values: Any) -> ModelT:
        values.pop("tenant_id", None)
        entity = self.model(tenant_id=self.tenant_id, **values)
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def delete(self, entity_id: UUID) -> bool:
        entity = await self.get(entity_id)
        if entity is None:
            return False
        await self.session.delete(entity)
        await self.session.flush()
        return True
