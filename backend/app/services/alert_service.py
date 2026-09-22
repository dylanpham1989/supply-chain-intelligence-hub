from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import Alert
from app.repositories.alert_repo import AlertRepository
from app.schemas.alert import AlertFilters


class AlertService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.repo = AlertRepository(session, tenant_id)

    async def search(self, filters: AlertFilters) -> tuple[Sequence[Alert], int]:
        return await self.repo.search(filters, limit=filters.size, offset=filters.offset)

    async def unread_count(self) -> int:
        return await self.repo.unread_count()

    async def mark_read(self, alert_id: UUID) -> Alert:
        alert = await self.repo.get(alert_id)
        if alert is None:
            raise NotFoundError("Alert not found")
        alert.is_read = True
        await self.session.flush()
        return alert

    async def mark_all_read(self) -> int:
        return await self.repo.mark_all_read()
