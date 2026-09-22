from collections.abc import Sequence

from sqlalchemy import func, or_, select

from app.models import Supplier
from app.repositories.base import TenantRepository
from app.schemas.supplier import SupplierFilters

SORT_COLUMNS = {
    "name": Supplier.name,
    "on_time_rate": Supplier.on_time_rate,
    "risk_score": Supplier.risk_score,
    "created_at": Supplier.created_at,
}


class SupplierRepository(TenantRepository[Supplier]):
    model = Supplier

    async def search(
        self, filters: SupplierFilters, *, limit: int, offset: int
    ) -> tuple[Sequence[Supplier], int]:
        stmt = self._scoped()
        if filters.country:
            stmt = stmt.where(Supplier.country == filters.country.upper())
        if filters.category:
            stmt = stmt.where(Supplier.category == filters.category)
        if filters.search:
            term = f"%{filters.search.strip()}%"
            stmt = stmt.where(or_(Supplier.name.ilike(term), Supplier.category.ilike(term)))

        column = SORT_COLUMNS[filters.sort]
        # Suppliers without stats sort last either way rather than bunching at
        # the top on a descending sort.
        ordering = (
            column.asc().nulls_last() if filters.order == "asc" else column.desc().nulls_last()
        )
        page = stmt.order_by(ordering, Supplier.id.desc()).limit(limit).offset(offset)

        rows = (await self.session.execute(page)).scalars().all()
        total = (
            await self.session.execute(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            )
        ).scalar_one()
        return rows, total

    async def by_name(self, name: str) -> Supplier | None:
        stmt = self._scoped().where(func.lower(Supplier.name) == name.strip().lower())
        return (await self.session.execute(stmt)).scalar_one_or_none()
