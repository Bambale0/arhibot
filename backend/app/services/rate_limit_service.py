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

    async def enforce_window(
        self,
        namespace: str,
        identity: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> None:
        if limit < 1 or window_seconds < 1:
            raise ValueError("Rate-limit window and limit must be positive.")
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        bucket = int(time.time() // window_seconds)
        key = f"auroom:rate:{namespace}:{digest}:{bucket}"
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, window_seconds + 10)
        if count > limit:
            raise AppError(
                type="rate_limit_exceeded",
                title="Too many requests",
                status=429,
                detail="Request limit exceeded. Please retry later.",
            )

    async def enforce_registration_daily(self, identity: str) -> None:
        settings = await self.repository.get()
        limit = settings.registration_rate_limit_per_day if settings is not None else 20
        await self.enforce_window(
            "register-day",
            identity,
            limit=limit,
            window_seconds=86_400,
        )

    async def enforce_asset_upload(self, identity: str) -> None:
        settings = await self.repository.get()
        limit = settings.asset_upload_rate_limit_per_minute if settings is not None else 12
        await self.enforce_window(
            "asset-upload",
            identity,
            limit=limit,
            window_seconds=60,
        )

    async def enforce_yookassa_webhook(self, identity: str) -> None:
        settings = await self.repository.get()
        limit = (
            settings.yookassa_webhook_rate_limit_per_minute
            if settings is not None
            else 120
        )
        await self.enforce_window(
            "yookassa-webhook",
            identity,
            limit=limit,
            window_seconds=60,
        )

    async def enforce(self, kind: RateLimitKind, identity: str) -> None:
        settings = await self.repository.get()
        defaults = {"auth": 30, "generation": 10, "payment": 10}
        limit = (
            {
                "auth": settings.auth_rate_limit_per_minute,
                "generation": settings.generation_rate_limit_per_minute,
                "payment": settings.payment_rate_limit_per_minute,
            }[kind]
            if settings is not None
            else defaults[kind]
        )

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
