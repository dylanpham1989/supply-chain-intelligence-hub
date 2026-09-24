"""Tenant-namespaced read-through cache.

The key always starts with the tenant, because row-level security does not reach
into redis. A key that omits the tenant hands one customer's dashboard to
another, and no policy will stop it.

Reads fail open. A cache that takes the API down with it is worse than a slow
API.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.logging import get_logger
from app.core.metrics import record_cache

log = get_logger(__name__)

# Bump when a cached payload's shape changes, instead of flushing redis.
SCHEMA_VERSION = "v1"
DEFAULT_TTL_S = 60
TAG_TTL_MARGIN_S = 60


def cache_key(tenant_id: UUID, prefix: str, params: dict[str, Any] | None = None) -> str:
    digest = ""
    if params:
        canonical = json.dumps(params, sort_keys=True, default=str, separators=(",", ":"))
        digest = ":" + hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return f"t:{tenant_id}:{prefix}:{SCHEMA_VERSION}{digest}"


def tag_key(tenant_id: UUID, tag: str) -> str:
    return f"t:{tenant_id}:tag:{tag}"


async def get_or_set[ModelT: BaseModel](
    redis: Redis,
    *,
    tenant_id: UUID,
    prefix: str,
    model: type[ModelT],
    loader: Callable[[], Awaitable[ModelT]],
    params: dict[str, Any] | None = None,
    ttl_s: int = DEFAULT_TTL_S,
    tags: Sequence[str] = (),
) -> tuple[ModelT, bool]:
    """Returns the value and whether it came from the cache."""
    key = cache_key(tenant_id, prefix, params)

    try:
        cached = await redis.get(key)
        if cached is not None:
            record_cache("hit")
            return model.model_validate_json(cached), True
        record_cache("miss")
    except (RedisError, ValueError) as exc:
        record_cache("error")
        log.warning("cache.read_failed", key=key, error=str(exc))

    value = await loader()

    try:
        pipe = redis.pipeline()
        pipe.set(key, value.model_dump_json(), ex=ttl_s)
        for tag in tags:
            # Remembering which keys carry a tag is what makes invalidation
            # possible without KEYS, which blocks redis while it scans.
            tk = tag_key(tenant_id, tag)
            pipe.sadd(tk, key)
            pipe.expire(tk, ttl_s + TAG_TTL_MARGIN_S)
        await pipe.execute()
    except RedisError as exc:
        log.warning("cache.write_failed", key=key, error=str(exc))

    return value, False


async def invalidate_tags(redis: Redis, tenant_id: UUID, tags: Sequence[str]) -> int:
    removed = 0
    try:
        for tag in tags:
            tk = tag_key(tenant_id, tag)
            keys: set[str] = await redis.smembers(tk)  # type: ignore[misc]
            if keys:
                removed += await redis.delete(*keys)
            await redis.delete(tk)
    except RedisError as exc:
        log.warning("cache.invalidate_failed", tenant_id=str(tenant_id), error=str(exc))
    return removed
