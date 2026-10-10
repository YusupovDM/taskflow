import hashlib
import json
import logging
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.metrics import cache_requests_total

logger = logging.getLogger(__name__)


def project_key(project_id: int) -> str:
    return f"project:{project_id}"


def tasks_version_key(project_id: int) -> str:
    return f"tasks:project:{project_id}:ver"


def tasks_list_key(project_id: int, version: int, params: dict[str, Any]) -> str:
    digest = hashlib.md5(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()
    return f"tasks:project:{project_id}:v{version}:{digest}"


def create_redis(url: str) -> Redis:
    # короткие таймауты: при недоступном Redis запрос не должен висеть
    return Redis.from_url(
        url, socket_timeout=0.5, socket_connect_timeout=0.5, decode_responses=True
    )


class Cache:
    """Обёртка над Redis с graceful degradation: любая ошибка Redis = промах кэша."""

    def __init__(self, redis: Redis | None) -> None:
        self.redis = redis

    async def get_json(self, key: str) -> Any | None:
        if self.redis is None:
            return None
        try:
            raw = await self.redis.get(key)
        except (RedisError, OSError) as exc:
            logger.warning("redis unavailable: %s", exc)
            cache_requests_total.labels(result="error").inc()
            return None  # идём в БД как будто промах
        cache_requests_total.labels(result="hit" if raw else "miss").inc()
        return json.loads(raw) if raw else None

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        if self.redis is None:
            return
        try:
            await self.redis.set(key, json.dumps(value, default=str), ex=ttl)
        except (RedisError, OSError) as exc:
            logger.warning("redis unavailable, cache not set: %s", exc)

    async def get_int(self, key: str) -> int:
        if self.redis is None:
            return 0
        try:
            raw = await self.redis.get(key)
        except (RedisError, OSError) as exc:
            logger.warning("redis unavailable: %s", exc)
            return 0
        return int(raw) if raw else 0

    async def delete(self, key: str) -> None:
        if self.redis is None:
            return
        try:
            await self.redis.delete(key)
        except (RedisError, OSError) as exc:
            logger.warning("redis unavailable, key %s not deleted: %s", key, exc)

    async def incr(self, key: str) -> None:
        if self.redis is None:
            return
        try:
            await self.redis.incr(key)
        except (RedisError, OSError) as exc:
            logger.warning("redis unavailable, key %s not incremented: %s", key, exc)

    async def ping(self) -> bool:
        if self.redis is None:
            return False
        try:
            return bool(await self.redis.ping())
        except (RedisError, OSError):
            return False

    async def close(self) -> None:
        if self.redis is not None:
            await self.redis.aclose()

    # --- инвалидация ---

    async def invalidate_project(self, project_id: int) -> None:
        await self.delete(project_key(project_id))

    async def invalidate_tasks(self, project_id: int) -> None:
        # старые ключи списков умрут по TTL — SCAN/KEYS не нужен
        await self.incr(tasks_version_key(project_id))
