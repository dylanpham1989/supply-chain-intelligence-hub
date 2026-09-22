from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, RedisClient
from app.core.errors import AuthError
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse
from app.schemas.user import UserRead
from app.services.auth_service import AuthService, IssuedTokens

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
# Narrow path: the cookie is only needed by the refresh and logout endpoints, so
# it is not attached to every other request.
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _service(session: DbSession, redis: RedisClient) -> AuthService:
    return AuthService(session, redis)


Service = Annotated[AuthService, Depends(_service)]


def _respond(response: Response, issued: IssuedTokens) -> TokenResponse:
    response.set_cookie(
        REFRESH_COOKIE,
        issued.refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        httponly=True,
        # http on localhost would drop a Secure cookie, and the login would fail
        # with no visible reason.
        secure=not settings.is_local,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
    )
    return TokenResponse(
        access_token=issued.access_token,
        expires_in=issued.expires_in,
        role=issued.user.role,
        tenant_slug=issued.tenant_slug,
    )


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, response: Response, service: Service) -> TokenResponse:
    return _respond(response, await service.signup(payload))


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, request: Request, response: Response, service: Service
) -> TokenResponse:
    client_ip = request.client.host if request.client else "unknown"
    return _respond(response, await service.login(payload, client_ip=client_ip))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    service: Service,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> TokenResponse:
    if not refresh_token:
        raise AuthError("Missing refresh token")
    return _respond(response, await service.refresh(refresh_token))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    service: Service,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> None:
    await service.logout(refresh_token)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
