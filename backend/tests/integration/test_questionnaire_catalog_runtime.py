import os

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip(
        "set RUN_INTEGRATION_TESTS=1 with a migrated test database", allow_module_level=True
    )

from app.main import app  # noqa: E402


@pytest.mark.asyncio
async def test_questionnaire_catalog_is_served_after_fresh_migrations() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/questionnaires")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["version"] == "2026-10-24.1"
    assert len(payload["questionnaires"]) == 27
    assert payload["questionnaires"][0]["key"] == "eskez-doma"

    house = payload["questionnaires"][0]
    heating = next(q for q in house["questions"] if q["id"] == "11б")
    assert heating["text"] == "Печное отопление?"
    assert set(heating["options"]) == {"Да", "Нет"}


@pytest.mark.asyncio
async def test_heating_migration_archives_custom_catalog_and_is_repeat_safe():
    from copy import deepcopy
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from app.db.models.questionnaires import (
        QuestionnaireCatalogConfig,
        QuestionnaireCatalogRevision,
    )
    from app.db.session import get_engine

    path = Path(__file__).parents[2] / "alembic/versions/20261024_0043_stove_heating.py"
    spec = spec_from_file_location("heating_migration", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    table = QuestionnaireCatalogConfig.__table__
    revisions = QuestionnaireCatalogRevision.__table__
    async with get_engine().connect() as connection:
        transaction = await connection.begin()
        try:
            current = (
                (await connection.execute(sa.select(table).where(table.c.id == 1))).mappings().one()
            )
            # Use a new target version inside the rolled-back test transaction.
            migration.VERSION = "integration-stove-target"
            old_version = "integration-stove-operator-catalog"
            old = deepcopy(current["catalog"])
            old["version"] = old_version
            house = old["questionnaires"][0]
            house["questions"][0]["text"] = "Custom operator style question"
            next(q for q in house["questions"] if q["id"] == "11б")["text"] = (
                "Будет ли камин в доме?"
            )
            await connection.execute(
                sa.update(table).where(table.c.id == 1).values(version=old_version, catalog=old)
            )

            def upgrade(sync_connection):
                migration.op = Operations(MigrationContext.configure(sync_connection))
                migration.upgrade()

            await connection.run_sync(upgrade)
            await connection.run_sync(upgrade)
            updated = (
                (await connection.execute(sa.select(table).where(table.c.id == 1))).mappings().one()
            )
            archived = (
                await connection.execute(
                    sa.select(revisions.c.catalog).where(revisions.c.version == old_version)
                )
            ).scalar_one()
            assert archived == old
            assert updated["version"] == migration.VERSION
            assert updated["catalog"]["questionnaires"][1:] == old["questionnaires"][1:]
            house = updated["catalog"]["questionnaires"][0]
            assert house["questions"][0]["text"] == "Custom operator style question"
            assert (
                next(q for q in house["questions"] if q["id"] == "11б")["text"]
                == "Печное отопление?"
            )
        finally:
            await transaction.rollback()
