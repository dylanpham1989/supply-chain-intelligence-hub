from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import set_actor
from app.core.errors import AuthError, ForbiddenError
from app.core.permissions import has_permission
from app.core.security import TokenClaims, decode_token
from app.db.rls import set_tenant_context
from app.db.session import SessionLocal
from app.models import User
from app.repositories.user_repo import UserRepository

bearer = HTTPBearer(auto_error=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


async def get_token_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> TokenClaims:
    if credentials is None:
        raise AuthError("Missing bearer token")
    return decode_token(credentials.credentials, expect="access")


async def get_current_user(
    claims: Annotated[TokenClaims, Depends(get_token_claims)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    # The tenant comes from a signature-verified claim and never from the request
    # body, query or a header. If a client could name its own tenant, none of the
    # isolation below it would mean anything.
    #
    # FastAPI caches a dependency per request, so this is the same session object
    # the route handler receives. It has to be: set_tenant_context is scoped to
    # one transaction, so setting it on a different session would leave the
    # handler's queries unscoped.
    await set_tenant_context(session, claims.tid)

    user = await UserRepository(session, claims.tid).get(claims.sub)
    if user is None or not user.is_active:
        raise AuthError()
    # From here on every log line and the access line carry who this was.
    set_actor(str(claims.tid), str(claims.sub))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_session)]
RedisClient = Annotated[Redis, Depends(get_redis)]


def require(*permissions: str) -> Callable[..., Coroutine[Any, Any, User]]:
    async def dependency(user: CurrentUser) -> User:
        for permission in permissions:
            if not has_permission(user.role, permission):
                raise ForbiddenError(f"Requires {permission}")
        return user

    return dependency
