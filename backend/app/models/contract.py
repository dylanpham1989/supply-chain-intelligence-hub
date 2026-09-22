from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import TenantEntity
from app.models.document import Document
from app.models.supplier import Supplier


class Contract(TenantEntity):
    __tablename__ = "contracts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "contract_number"),
        Index("ix_contracts_tenant_expiry", "tenant_id", "effective_to"),
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    contract_number: Mapped[str] = mapped_column(String(64), nullable=False)
    supplier_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL")
    )
    document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    penalty_terms: Mapped[str | None] = mapped_column(Text)

    supplier: Mapped[Supplier | None] = relationship(lazy="raise")
    document: Mapped[Document | None] = relationship(lazy="raise")

    def __repr__(self) -> str:
        return f"<Contract {self.contract_number}>"
