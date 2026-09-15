import pytest_asyncio

from app.core.redis import redis_client
from app.db.models.operations import OperationalSettings
from app.db.session import dispose_engine, get_session_factory


@pytest_asyncio.fixture(autouse=True)
async def reset_async_clients_between_tests():
    """Keep async clients loop-safe and prevent the shared test IP from exhausting prod-safe limits."""
    await redis_client.aclose()
    await dispose_engine()
    async with get_session_factory()() as session:
        settings = await session.get(OperationalSettings, 1)
        if settings is not None:
            settings.auth_rate_limit_per_minute = 100_000
            settings.generation_rate_limit_per_minute = 100_000
            settings.payment_rate_limit_per_minute = 100_000
            settings.registration_rate_limit_per_day = 100_000
            settings.yookassa_webhook_rate_limit_per_minute = 100_000
            settings.asset_upload_rate_limit_per_minute = 100_000
            settings.generation_max_inflight_per_user = 100_000
            settings.initial_concept_offer_limit_per_day = 100_000
            await session.commit()
    yield
    await redis_client.aclose()
    await dispose_engine()
