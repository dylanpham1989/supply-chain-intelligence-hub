import time
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.errors import RateLimitError
from app.core.logging import get_logger

log = get_logger(__name__)


async def enforce(redis: Redis, key: str, *, limit: int, window_s: int) -> None:
    """Sliding window over a sorted set, scored by timestamp.

    Fails open. A rate limiter that takes the API down with it is worse than one
    that occasionally lets a burst through.
    """
    now = time.time()
    try:
        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - window_s)
        pipe.zadd(key, {str(uuid4()): now})
        pipe.zcard(key)
        pipe.expire(key, window_s)
        _, _, count, _ = await pipe.execute()
    except RedisError as exc:
        log.warning("ratelimit.unavailable", key=key, error=str(exc))
        return

    if count > limit:
        raise RateLimitError()
