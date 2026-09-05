import pytest_asyncio

from app.core.redis import redis_client
from app.db.session import dispose_engine


@pytest_asyncio.fixture(autouse=True)
async def reset_async_clients_between_tests():
    """Keep loop-bound asyncpg/Redis clients scoped to the current pytest loop."""
    await redis_client.aclose()
    await dispose_engine()
    yield
    await redis_client.aclose()
    await dispose_engine()
