from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.config import settings
from app.core.errors import AuthError, ConflictError
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    new_token_family,
    verify_password,
    verify_password_dummy,
)
from app.db.rls import set_tenant_context
from app.models import RefreshToken, Tenant, User
from app.models.enums import UserRole
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository
from app.schemas.auth import LoginRequest, SignupRequest

log = get_logger(__name__)

LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_WINDOW_S = 15 * 60


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    user: User
    tenant_slug: str
    stored_refresh_id: UUID


class AuthService:
    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self.session = session
        self.redis = redis

    async def signup(self, payload: SignupRequest) -> IssuedTokens:
        tenant = Tenant(slug=payload.tenant_slug, name=payload.company_name)
        self.session.add(tenant)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("That workspace name is taken") from exc

        # Everything after this point writes tenant-owned rows, which the policy
        # rejects without a tenant in scope.
        await set_tenant_context(self.session, tenant.id)

        user = User(
            tenant_id=tenant.id,
            email=str(payload.email).lower(),
            password_hash=await hash_password(payload.password),
            full_name=payload.full_name,
            role=UserRole.ADMIN,
        )
        self.session.add(user)
        await self.session.flush()

        log.info("auth.signup", tenant_id=str(tenant.id), tenant_slug=tenant.slug)
        return await self._issue(user, tenant.slug, family_id=None)

    async def login(self, payload: LoginRequest, *, client_ip: str) -> IssuedTokens:
        await ratelimit.enforce(
            self.redis,
            f"rl:login:{payload.tenant_slug}:{str(payload.email).lower()}:{client_ip}",
            limit=LOGIN_ATTEMPT_LIMIT,
            window_s=LOGIN_ATTEMPT_WINDOW_S,
        )

        tenant = await self._tenant_by_slug(payload.tenant_slug)
        if tenant is None:
            # Still pay the hashing cost, so a wrong workspace is not faster than
            # a wrong password.
            await verify_password_dummy(payload.password)
            raise AuthError()

        await set_tenant_context(self.session, tenant.id)
        user = await UserRepository(self.session, tenant.id).by_email(str(payload.email))

        if user is None:
            await verify_password_dummy(payload.password)
            raise AuthError()
        if not await verify_password(payload.password, user.password_hash):
            log.info("auth.login.failed", tenant_id=str(tenant.id), user_id=str(user.id))
            raise AuthError()
        if not user.is_active:
            raise AuthError()

        user.last_login_at = datetime.now(UTC)
        pruned = await RefreshTokenRepository(self.session, tenant.id).prune_for_user(user.id)
        await self.session.flush()

        log.info(
            "auth.login",
            tenant_id=str(tenant.id),
            user_id=str(user.id),
            role=user.role,
            pruned_tokens=pruned,
        )
        return await self._issue(user, tenant.slug, family_id=None)

    async def refresh(self, raw_token: str) -> IssuedTokens:
        claims = decode_token(raw_token, expect="refresh")
        await set_tenant_context(self.session, claims.tid)

        repo = RefreshTokenRepository(self.session, claims.tid)
        stored = await repo.by_hash(hash_token(raw_token))
        if stored is None:
            raise AuthError("Invalid token")

        if stored.is_revoked:
            # A revoked token being presented again means someone else has a copy.
            # The legitimate holder will have to log in; that is the point.
            revoked = await repo.revoke_family(stored.family_id)
            log.warning(
                "auth.refresh.reuse_detected",
                tenant_id=str(claims.tid),
                user_id=str(stored.user_id),
                family_id=str(stored.family_id),
                revoked=revoked,
            )
            raise AuthError("Invalid token")

        if stored.expires_at <= datetime.now(UTC):
            raise AuthError("Invalid token")

        user = await UserRepository(self.session, claims.tid).get(stored.user_id)
        if user is None or not user.is_active:
            raise AuthError()

        issued = await self._issue(user, claims.tslug, family_id=stored.family_id)
        await repo.mark_replaced(stored, issued.stored_refresh_id)
        return issued

    async def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        try:
            claims = decode_token(raw_token, expect="refresh")
        except AuthError:
            return

        await set_tenant_context(self.session, claims.tid)
        repo = RefreshTokenRepository(self.session, claims.tid)
        stored = await repo.by_hash(hash_token(raw_token))
        if stored is None:
            return
        await repo.revoke_family(stored.family_id)
        log.info("auth.logout", tenant_id=str(claims.tid), user_id=str(stored.user_id))

    async def _tenant_by_slug(self, slug: str) -> Tenant | None:
        stmt = select(Tenant).where(
            func.lower(Tenant.slug) == slug.strip().lower(), Tenant.is_active.is_(True)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _issue(self, user: User, tenant_slug: str, *, family_id: UUID | None) -> IssuedTokens:
        access = create_access_token(
            user_id=user.id, tenant_id=user.tenant_id, tenant_slug=tenant_slug, role=user.role
        )
        raw_refresh, _, expires_at = create_refresh_token(
            user_id=user.id, tenant_id=user.tenant_id, tenant_slug=tenant_slug, role=user.role
        )

        stored = RefreshToken(
            tenant_id=user.tenant_id,
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            family_id=family_id or new_token_family(),
            expires_at=expires_at,
        )
        self.session.add(stored)
        await self.session.flush()

        return IssuedTokens(
            access_token=access,
            refresh_token=raw_refresh,
            expires_in=settings.access_token_ttl_min * 60,
            user=user,
            tenant_slug=tenant_slug,
            stored_refresh_id=stored.id,
        )
