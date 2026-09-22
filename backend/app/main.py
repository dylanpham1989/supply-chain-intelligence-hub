"""FastAPI application entrypoint."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, TypedDict

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.db.session import engine

log = get_logger(__name__)

DEPENDENCY_TIMEOUT_S = 2.0

HTTP_ERROR_CODES = {
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    429: "rate_limited",
}


class HealthPayload(TypedDict):
    status: str
    db: bool
    redis: bool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(env=settings.env, level="DEBUG" if settings.debug else "INFO")

    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)

    app.state.engine = engine
    app.state.redis = redis
    log.info("app.startup", env=settings.env, vector_backend=settings.vector_backend)

    try:
        yield
    finally:
        await redis.aclose()
        await engine.dispose()
        log.info("app.shutdown")


def create_app() -> FastAPI:
    # CI generates the frontend types off this, but prod does not need to publish it.
    expose_schema = settings.env in ("local", "test", "staging")

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if expose_schema else None,
        redoc_url=None,
        openapi_url="/openapi.json" if expose_schema else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    if expose_schema:

        @app.get("/", include_in_schema=False)
        async def root() -> RedirectResponse:
            return RedirectResponse(url="/docs")

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        log.warning(
            "request.failed",
            code=exc.code,
            status=exc.status_code,
            path=request.url.path,
            **exc.extra,
        )
        # No stack trace to the client; it goes to the log instead.
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Same envelope as everything else, so a client branches on one shape.
        fields = [
            {"field": ".".join(str(p) for p in err["loc"][1:]), "problem": err["msg"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"code": "validation_error", "message": "Request is invalid", "fields": fields},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": HTTP_ERROR_CODES.get(exc.status_code, "error"),
                "message": str(exc.detail),
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("request.unhandled", path=request.url.path, error=str(exc))
        # The traceback goes to the log, never to the caller.
        return JSONResponse(
            status_code=500,
            content={"code": "internal_error", "message": "Internal server error"},
        )

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["health"])
    async def health() -> JSONResponse:
        db_ok, redis_ok = await asyncio.gather(
            _check("db", _ping_db, app.state.engine),
            _check("redis", _ping_redis, app.state.redis),
        )
        payload: HealthPayload = {
            "status": "ok" if db_ok and redis_ok else "degraded",
            "db": db_ok,
            "redis": redis_ok,
        }
        return JSONResponse(
            content=dict(payload),
            status_code=200 if db_ok and redis_ok else 503,
        )

    return app


async def _check(name: str, probe: Callable[[Any], Awaitable[None]], resource: Any) -> bool:
    try:
        await asyncio.wait_for(probe(resource), timeout=DEPENDENCY_TIMEOUT_S)
    except Exception as exc:
        log.warning("health.dependency_failed", dependency=name, error=str(exc))
        return False
    return True


async def _ping_db(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _ping_redis(redis: Redis) -> None:
    await redis.ping()


app = create_app()
