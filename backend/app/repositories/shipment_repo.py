from collections.abc import Sequence

from sqlalchemy import Select, func, or_, select

from app.models import Shipment
from app.repositories.base import TenantRepository
from app.schemas.shipment import ShipmentFilters

# Whitelist. Never getattr(Shipment, user_input).
SORT_COLUMNS = {
    "created_at": Shipment.created_at,
    "eta": Shipment.eta,
    "value_usd": Shipment.value_usd,
    "reference": Shipment.reference,
}


class ShipmentRepository(TenantRepository[Shipment]):
    model = Shipment

    def _filtered(self, filters: ShipmentFilters) -> Select[tuple[Shipment]]:
        stmt = self._scoped()
        if filters.status is not None:
            stmt = stmt.where(Shipment.status == filters.status)
        if filters.mode is not None:
            stmt = stmt.where(Shipment.mode == filters.mode)
        if filters.risk_label is not None:
            stmt = stmt.where(Shipment.risk_label == filters.risk_label)
        if filters.supplier_id is not None:
            stmt = stmt.where(Shipment.supplier_id == filters.supplier_id)
        if filters.origin_country:
            stmt = stmt.where(Shipment.origin_country == filters.origin_country.upper())
        if filters.dest_country:
            stmt = stmt.where(Shipment.dest_country == filters.dest_country.upper())
        if filters.eta_from is not None:
            stmt = stmt.where(Shipment.eta >= filters.eta_from)
        if filters.eta_to is not None:
            stmt = stmt.where(Shipment.eta <= filters.eta_to)
        if filters.late_only:
            stmt = stmt.where(Shipment.ata.is_not(None), Shipment.ata > Shipment.eta)
        if filters.search:
            term = f"%{filters.search.strip()}%"
            stmt = stmt.where(
                or_(
                    Shipment.reference.ilike(term),
                    Shipment.origin_country.ilike(term),
                    Shipment.dest_country.ilike(term),
                )
            )
        return stmt

    async def search(
        self, filters: ShipmentFilters, *, limit: int, offset: int
    ) -> tuple[Sequence[Shipment], int]:
        stmt = self._filtered(filters)

        column = SORT_COLUMNS[filters.sort]
        ordering = column.asc() if filters.order == "asc" else column.desc()
        # Tie-break on the primary key so paging cannot repeat or skip a row when
        # the sort column has duplicates.
        page = stmt.order_by(ordering, Shipment.id.desc()).limit(limit).offset(offset)

        rows = (await self.session.execute(page)).scalars().all()
        total = (
            await self.session.execute(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            )
        ).scalar_one()
        return rows, total

    async def by_reference(self, reference: str) -> Shipment | None:
        stmt = self._scoped().where(Shipment.reference == reference)
        return (await self.session.execute(stmt)).scalar_one_or_none()
