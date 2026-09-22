from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_or_set
from app.repositories.analytics_repo import AnalyticsRepository
from app.schemas.analytics import (
    RiskBreakdown,
    RiskSlice,
    StatusBreakdown,
    StatusCount,
    Summary,
    SupplierRanking,
    Timeseries,
    TimeseriesPoint,
    TopSuppliers,
)

CACHE_TAG = "analytics"
SUMMARY_TTL_S = 60


class AnalyticsService:
    def __init__(self, session: AsyncSession, redis: Redis, tenant_id: UUID) -> None:
        self.repo = AnalyticsRepository(session, tenant_id)
        self.redis = redis
        self.tenant_id = tenant_id

    @staticmethod
    def window_start(days: int) -> date:
        return (datetime.now(UTC) - timedelta(days=days)).date()

    async def summary(self, days: int) -> tuple[Summary, bool]:
        since = self.window_start(days)

        async def load() -> Summary:
            row = await self.repo.summary(since)
            return Summary(
                total_shipments=row["total_shipments"],
                delayed=row["delayed"],
                in_transit=row["in_transit"],
                delivered=row["delivered"],
                total_value_usd=row["total_value_usd"],
                on_time_rate=row["on_time_rate"],
                avg_delay_days=float(row["avg_delay_days"]) if row["avg_delay_days"] else None,
                since=since,
            )

        return await get_or_set(
            self.redis,
            tenant_id=self.tenant_id,
            prefix="analytics:summary",
            model=Summary,
            loader=load,
            params={"days": days},
            ttl_s=SUMMARY_TTL_S,
            tags=[CACHE_TAG],
        )

    async def by_status(self, days: int) -> tuple[StatusBreakdown, bool]:
        since = self.window_start(days)

        async def load() -> StatusBreakdown:
            rows = await self.repo.by_status(since)
            return StatusBreakdown(items=[StatusCount(**dict(r)) for r in rows])

        return await get_or_set(
            self.redis,
            tenant_id=self.tenant_id,
            prefix="analytics:by-status",
            model=StatusBreakdown,
            loader=load,
            params={"days": days},
            tags=[CACHE_TAG],
        )

    async def timeseries(self, days: int) -> tuple[Timeseries, bool]:
        since = self.window_start(days)

        async def load() -> Timeseries:
            rows = await self.repo.timeseries(since)
            return Timeseries(items=[TimeseriesPoint(**dict(r)) for r in rows])

        return await get_or_set(
            self.redis,
            tenant_id=self.tenant_id,
            prefix="analytics:timeseries",
            model=Timeseries,
            loader=load,
            params={"days": days},
            tags=[CACHE_TAG],
        )

    async def top_suppliers(self, limit: int) -> tuple[TopSuppliers, bool]:
        async def load() -> TopSuppliers:
            rows = await self.repo.top_suppliers(limit)
            return TopSuppliers(items=[SupplierRanking(**dict(r)) for r in rows])

        return await get_or_set(
            self.redis,
            tenant_id=self.tenant_id,
            prefix="analytics:top-suppliers",
            model=TopSuppliers,
            loader=load,
            params={"limit": limit},
            tags=[CACHE_TAG],
        )

    async def risk_breakdown(self, days: int) -> tuple[RiskBreakdown, bool]:
        since = self.window_start(days)

        async def load() -> RiskBreakdown:
            rows = await self.repo.risk_breakdown(since)
            return RiskBreakdown(items=[RiskSlice(**dict(r)) for r in rows])

        return await get_or_set(
            self.redis,
            tenant_id=self.tenant_id,
            prefix="analytics:risk",
            model=RiskBreakdown,
            loader=load,
            params={"days": days},
            tags=[CACHE_TAG],
        )
