from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings

pool = ConnectionPool.from_url(settings.redis_url, decode_responses=True, max_connections=20)


def create_redis() -> Redis:
    return Redis(connection_pool=pool)
