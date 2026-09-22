from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import TenantEntity


class RefreshToken(TenantEntity):
    """One issued refresh token.

    Tokens are rotated: using one revokes it and issues a replacement in the same
    family. Presenting an already revoked token means it leaked, so the whole
    family is killed rather than just that token.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_tenant_user", "tenant_id", "user_id"),
        Index("ix_refresh_tokens_family", "family_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # sha256 of the token, never the token itself.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    family_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    user_agent: Mapped[str | None] = mapped_column(String(256))

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None
