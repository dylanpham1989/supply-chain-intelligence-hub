"""FastAPI application entrypoint."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, TypedDict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import settings
from app.core.logging import configure_logging, get_logger

log = get_logger(__name__)

DEPENDENCY_TIMEOUT_S = 2.0


class HealthPayload(TypedDict):
    status: str
    db: bool
    redis: bool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(env=settings.env, level="DEBUG" if settings.debug else "INFO")

    engine = create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        echo=False,
    )
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
    # Schema and interactive docs are useful while developing and in CI, where the
    # frontend types are generated from them, but they describe the whole attack
    # surface so they stay off in deployed environments.
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
    """Run one dependency probe. Any failure means unhealthy, never an exception."""
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
