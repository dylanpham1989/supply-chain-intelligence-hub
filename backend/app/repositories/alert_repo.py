from collections.abc import Sequence

from sqlalchemy import CursorResult, func, select, update

from app.models import Alert
from app.repositories.base import TenantRepository
from app.schemas.alert import AlertFilters


class AlertRepository(TenantRepository[Alert]):
    model = Alert

    async def search(
        self, filters: AlertFilters, *, limit: int, offset: int
    ) -> tuple[Sequence[Alert], int]:
        stmt = self._scoped()
        if filters.kind is not None:
            stmt = stmt.where(Alert.kind == filters.kind)
        if filters.severity is not None:
            stmt = stmt.where(Alert.severity == filters.severity)
        if filters.unread_only:
            stmt = stmt.where(Alert.is_read.is_(False))

        page = stmt.order_by(Alert.created_at.desc(), Alert.id.desc()).limit(limit).offset(offset)
        rows = (await self.session.execute(page)).scalars().all()
        total = (
            await self.session.execute(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            )
        ).scalar_one()
        return rows, total

    async def unread_count(self) -> int:
        stmt = (
            select(func.count())
            .select_from(Alert)
            .where(Alert.tenant_id == self.tenant_id, Alert.is_read.is_(False))
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def mark_all_read(self) -> int:
        stmt = (
            update(Alert)
            .where(Alert.tenant_id == self.tenant_id, Alert.is_read.is_(False))
            .values(is_read=True)
        )
        result: CursorResult[None] = await self.session.execute(stmt)  # type: ignore[assignment]
        return result.rowcount
