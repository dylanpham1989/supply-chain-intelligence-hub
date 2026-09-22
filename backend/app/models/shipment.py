from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import TenantEntity
from app.models.enums import RiskLabel, ShipmentStatus, TransportMode, pg_enum
from app.models.supplier import Supplier


class Shipment(TenantEntity):
    __tablename__ = "shipments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "reference"),
        # tenant_id leads every index: it is in every query and has the highest
        # selectivity, so the planner can use these for filtered reads.
        Index("ix_shipments_tenant_created", "tenant_id", "created_at"),
        Index("ix_shipments_tenant_status", "tenant_id", "status"),
        Index("ix_shipments_tenant_eta", "tenant_id", "eta"),
    )

    reference: Mapped[str] = mapped_column(String(64), nullable=False)
    supplier_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL")
    )
    origin_country: Mapped[str] = mapped_column(String(2), nullable=False)
    dest_country: Mapped[str] = mapped_column(String(2), nullable=False)
    mode: Mapped[TransportMode] = mapped_column(
        pg_enum(TransportMode, "transport_mode"), nullable=False
    )
    incoterm: Mapped[str | None] = mapped_column(String(8))
    qty: Mapped[int] = mapped_column(nullable=False, default=0)
    value_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    eta: Mapped[date] = mapped_column(Date, nullable=False)
    ata: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ShipmentStatus] = mapped_column(
        pg_enum(ShipmentStatus, "shipment_status"), nullable=False
    )
    risk_label: Mapped[RiskLabel | None] = mapped_column(pg_enum(RiskLabel, "risk_label"))
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))

    supplier: Mapped[Supplier | None] = relationship(lazy="raise")

    @property
    def delay_days(self) -> int | None:
        if self.ata is None:
            return None
        return (self.ata - self.eta).days

    def __repr__(self) -> str:
        return f"<Shipment {self.reference} {self.status}>"
