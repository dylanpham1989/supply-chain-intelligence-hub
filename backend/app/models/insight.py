from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import TenantEntity


class Insight(TenantEntity):
    """One answered question, kept for history and for cost accounting."""

    __tablename__ = "insights"
    __table_args__ = (Index("ix_insights_tenant_created", "tenant_id", "created_at"),)

    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    route: Mapped[str] = mapped_column(String(32), nullable=False, default="semantic")
    model: Mapped[str | None] = mapped_column(String(128))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    token_in: Mapped[int | None] = mapped_column(Integer)
    token_out: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
