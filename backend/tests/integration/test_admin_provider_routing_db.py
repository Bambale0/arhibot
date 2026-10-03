import os
from uuid import uuid4

import pytest
from sqlalchemy import insert, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip(
        "set RUN_INTEGRATION_TESTS=1 with a migrated test database",
        allow_module_level=True,
    )

from app.db.models.admin import GenerationRuntimeSettings  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402


@pytest.mark.asyncio
async def test_migrated_provider_defaults_preserve_legacy_routing() -> None:
    async with get_session_factory()() as session:
        result = await session.execute(
            text(
                "INSERT INTO generation_runtime_settings (id, primary_model) "
                "VALUES (:id, :model) RETURNING primary_provider, fallback_provider"
            ),
            {"id": -(uuid4().int % 1_000_000_000 + 1), "model": "test-image-model"},
        )
        assert result.one() == ("nexus", "nexus")
        await session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["primary_provider", "fallback_provider"])
async def test_migrated_provider_checks_reject_unknown_routing(field: str) -> None:
    async with get_session_factory()() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                insert(GenerationRuntimeSettings).values(
                    id=-(uuid4().int % 1_000_000_000 + 1),
                    primary_model="test-image-model",
                    **{field: "unknown"},
                )
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_migrated_provider_columns_accept_neironych_routing() -> None:
    async with get_session_factory()() as session:
        result = await session.execute(
            insert(GenerationRuntimeSettings)
            .values(
                id=-(uuid4().int % 1_000_000_000 + 1),
                primary_model="test-image-model",
                primary_provider="neironych",
                fallback_provider="nexus",
            )
            .returning(
                GenerationRuntimeSettings.primary_provider,
                GenerationRuntimeSettings.fallback_provider,
            )
        )
        assert result.one() == ("neironych", "nexus")
        await session.rollback()
