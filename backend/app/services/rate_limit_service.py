from __future__ import annotations

import hashlib
import time
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.redis import redis_client
from app.repositories.operations import OperationalSettingsRepository

RateLimitKind = Literal["auth", "generation", "payment"]


class RateLimitService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = OperationalSettingsRepository(session)

    async def enforce(self, kind: RateLimitKind, identity: str) -> None:
        settings = await self.repository.get()
        if settings is None:
            return
        limit = {
            "auth": settings.auth_rate_limit_per_minute,
            "generation": settings.generation_rate_limit_per_minute,
            "payment": settings.payment_rate_limit_per_minute,
        }[kind]
        if limit is None:
            return

        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        minute_bucket = int(time.time() // 60)
        key = f"auroom:rate:{kind}:{digest}:{minute_bucket}"
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, 70)
        if count > limit:
            raise AppError(
                type="rate_limit_exceeded",
                title="Too many requests",
                status=429,
                detail="Request limit exceeded. Please retry shortly.",
            )
