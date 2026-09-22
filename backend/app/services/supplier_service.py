from collections.abc import Sequence
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import invalidate_tags
from app.core.errors import ConflictError, NotFoundError
from app.models import Supplier
from app.repositories.analytics_repo import AnalyticsRepository
from app.repositories.supplier_repo import SupplierRepository
from app.schemas.supplier import (
    SupplierCreate,
    SupplierFilters,
    SupplierMonth,
    SupplierPerformance,
)


class SupplierService:
    def __init__(self, session: AsyncSession, redis: Redis, tenant_id: UUID) -> None:
        self.session = session
        self.redis = redis
        self.tenant_id = tenant_id
        self.repo = SupplierRepository(session, tenant_id)
        self.analytics = AnalyticsRepository(session, tenant_id)

    async def search(self, filters: SupplierFilters) -> tuple[Sequence[Supplier], int]:
        return await self.repo.search(filters, limit=filters.size, offset=filters.offset)

    async def get(self, supplier_id: UUID) -> Supplier:
        supplier = await self.repo.get(supplier_id)
        if supplier is None:
            raise NotFoundError("Supplier not found")
        return supplier

    async def create(self, payload: SupplierCreate) -> Supplier:
        if await self.repo.by_name(payload.name):
            raise ConflictError(f"Supplier {payload.name} already exists")
        data = payload.model_dump()
        data["country"] = data["country"].upper()
        supplier = await self.repo.create(**data)
        await invalidate_tags(self.redis, self.tenant_id, ["analytics"])
        return supplier

    async def performance(self, supplier_id: UUID) -> SupplierPerformance:
        supplier = await self.get(supplier_id)
        totals = await self.analytics.supplier_performance(supplier_id)
        monthly = await self.analytics.supplier_monthly(supplier_id)

        return SupplierPerformance(
            supplier_id=supplier.id,
            name=supplier.name,
            shipments=totals["shipments"],
            delivered=totals["delivered"],
            late=totals["late"],
            on_time_rate=totals["on_time_rate"],
            avg_delay_days=(float(totals["avg_delay_days"]) if totals["avg_delay_days"] else None),
            monthly=[SupplierMonth(**dict(m)) for m in monthly],
        )
