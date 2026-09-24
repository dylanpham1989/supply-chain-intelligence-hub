"""Liveness, readiness and build info.

The split matters in Kubernetes. Liveness answers "is this process wedged?" and
a failure restarts the pod. Readiness answers "can this pod serve traffic right
now?" and a failure only takes it out of the load balancer.

Checking the database in the liveness probe is the classic way to turn a slow
database into an outage: every pod fails its probe, Kubernetes restarts all of
them at once, the reconnect storm makes the database slower, and the cluster
never converges. So /health/live touches nothing.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings
from app.core.logging import get_logger
from app.core.storage import get_store

log = get_logger(__name__)
router = APIRouter(tags=["health"])

# A probe that can hang is a probe that fails the whole check, so each
# dependency gets its own budget and they run concurrently.
DEPENDENCY_TIMEOUT_S = 2.0


@router.get("/health/live", summary="Liveness probe")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/info", summary="Build info")
async def info() -> dict[str, str]:
    return {
        "version": settings.app_version,
        "git_sha": settings.git_sha,
        "built_at": settings.built_at,
        "env": settings.env,
    }


@router.get("/health/ready", summary="Readiness probe")
async def ready(request: Request) -> JSONResponse:
    return await _readiness(request)


@router.get("/health", summary="Readiness probe (alias)")
async def health(request: Request) -> JSONResponse:
    return await _readiness(request)


async def _readiness(request: Request) -> JSONResponse:
    names = ("db", "redis", "s3")
    results = await asyncio.gather(
        _check(_ping_db, request.app.state.engine),
        _check(_ping_redis, request.app.state.redis),
        _check(_ping_s3, None),
    )
    checks = dict(zip(names, results, strict=True))
    for name, ok in checks.items():
        if not ok:
            log.warning("health.dependency_failed", dependency=name)

    ready_now = all(checks.values())
    return JSONResponse(
        content={"status": "ok" if ready_now else "degraded", **checks},
        status_code=200 if ready_now else 503,
    )


async def _check(probe: Callable[[Any], Awaitable[None]], resource: Any) -> bool:
    try:
        await asyncio.wait_for(probe(resource), timeout=DEPENDENCY_TIMEOUT_S)
    except Exception:
        return False
    return True


async def _ping_db(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _ping_redis(redis: Redis) -> None:
    await redis.ping()


async def _ping_s3(_: Any) -> None:
    await get_store().ping()
