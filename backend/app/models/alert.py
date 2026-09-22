from uuid import UUID

from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import TenantEntity
from app.models.enums import AlertKind, AlertSeverity, pg_enum


class Alert(TenantEntity):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_tenant_created", "tenant_id", "created_at"),
        # The unread badge is the hottest query, and most rows are read.
        Index(
            "ix_alerts_tenant_unread",
            "tenant_id",
            "created_at",
            postgresql_where="is_read = false",
        ),
    )

    kind: Mapped[AlertKind] = mapped_column(pg_enum(AlertKind, "alert_kind"), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(
        pg_enum(AlertSeverity, "alert_severity"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    is_read: Mapped[bool] = mapped_column(nullable=False, default=False)

    def __repr__(self) -> str:
        return f"<Alert {self.kind} {self.severity}>"
