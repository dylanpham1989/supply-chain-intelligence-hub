from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import CursorResult, update

from app.models import RefreshToken
from app.repositories.base import TenantRepository


class RefreshTokenRepository(TenantRepository[RefreshToken]):
    model = RefreshToken

    async def by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = self._scoped().where(RefreshToken.token_hash == token_hash)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def revoke_family(self, family_id: UUID) -> int:
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.tenant_id == self.tenant_id,
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        result: CursorResult[None] = await self.session.execute(stmt)  # type: ignore[assignment]
        return result.rowcount

    async def mark_replaced(self, token: RefreshToken, replacement_id: UUID) -> None:
        token.revoked_at = datetime.now(UTC)
        token.replaced_by_id = replacement_id
        await self.session.flush()
