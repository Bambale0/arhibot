from typing import Any

from app.core.config import get_settings


class LazyRedisClient:
    """Avoid network/client initialization during OpenAPI generation and unit-test imports."""

    def __init__(self) -> None:
        self._client: Any | None = None

    def _get(self) -> Any:
        if self._client is None:
            from redis.asyncio import Redis

            settings = get_settings()
            self._client = Redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._client

    async def ping(self) -> bool:
        return bool(await self._get().ping())

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()


redis_client = LazyRedisClient()
