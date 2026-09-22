from collections.abc import Sequence
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import invalidate_tags
from app.core.errors import ConflictError, NotFoundError
from app.models import Alert, Shipment
from app.models.enums import AlertKind, AlertSeverity, ShipmentStatus
from app.repositories.alert_repo import AlertRepository
from app.repositories.shipment_repo import ShipmentRepository
from app.schemas.shipment import ShipmentCreate, ShipmentFilters, ShipmentUpdate

# Anything that changes shipment rows changes the dashboard built from them.
WRITE_TAGS = ("analytics", "shipments")


class ShipmentService:
    def __init__(self, session: AsyncSession, redis: Redis, tenant_id: UUID) -> None:
        self.session = session
        self.redis = redis
        self.tenant_id = tenant_id
        self.repo = ShipmentRepository(session, tenant_id)
        self.alerts = AlertRepository(session, tenant_id)

    async def search(self, filters: ShipmentFilters) -> tuple[Sequence[Shipment], int]:
        return await self.repo.search(filters, limit=filters.size, offset=filters.offset)

    async def get(self, shipment_id: UUID) -> Shipment:
        shipment = await self.repo.get(shipment_id)
        if shipment is None:
            raise NotFoundError("Shipment not found")
        return shipment

    async def create(self, payload: ShipmentCreate) -> Shipment:
        if await self.repo.by_reference(payload.reference):
            raise ConflictError(f"Shipment {payload.reference} already exists")

        data = payload.model_dump()
        data["origin_country"] = data["origin_country"].upper()
        data["dest_country"] = data["dest_country"].upper()
        shipment = await self.repo.create(**data)

        await self._raise_alert_if_late(shipment)
        await self._invalidate()
        return shipment

    async def update(self, shipment_id: UUID, payload: ShipmentUpdate) -> Shipment:
        shipment = await self.get(shipment_id)
        was_delayed = shipment.status == ShipmentStatus.DELAYED

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(shipment, field, value)
        await self.session.flush()

        if not was_delayed:
            await self._raise_alert_if_late(shipment)
        await self._invalidate()
        return shipment

    async def delete(self, shipment_id: UUID) -> None:
        if not await self.repo.delete(shipment_id):
            raise NotFoundError("Shipment not found")
        await self._invalidate()

    async def _raise_alert_if_late(self, shipment: Shipment) -> None:
        if shipment.status != ShipmentStatus.DELAYED:
            return
        delay = shipment.delay_days
        self.session.add(
            Alert(
                tenant_id=self.tenant_id,
                kind=AlertKind.LATE_DELIVERY,
                severity=AlertSeverity.HIGH if (delay or 0) > 7 else AlertSeverity.MEDIUM,
                title=f"{shipment.reference} is delayed",
                body=(
                    f"Lane {shipment.origin_country} to {shipment.dest_country}"
                    + (f", {delay} days late" if delay else "")
                ),
                entity_type="shipment",
                entity_id=shipment.id,
            )
        )
        await self.session.flush()

    async def _invalidate(self) -> None:
        await invalidate_tags(self.redis, self.tenant_id, WRITE_TAGS)
