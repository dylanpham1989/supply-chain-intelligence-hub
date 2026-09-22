from decimal import Decimal

from sqlalchemy import Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import TenantEntity


class Supplier(TenantEntity):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name"),
        Index("ix_suppliers_tenant_risk", "tenant_id", "risk_score"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(320))
    # Denormalised from shipments so dashboard cards do not aggregate on every load.
    on_time_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))

    def __repr__(self) -> str:
        return f"<Supplier {self.name}>"
