import os
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip("set RUN_INTEGRATION_TESTS=1 with a migrated test database", allow_module_level=True)

from app.db.models.assets import Asset  # noqa: E402
from app.db.models.generations import Generation  # noqa: E402
from app.db.models.users import AuthIdentity, User  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.domain.assets.enums import AssetPurpose, AssetType  # noqa: E402
from app.domain.generations.enums import GenerationStatus, GenerationType  # noqa: E402
from app.domain.users.enums import AuthProvider, UserRole  # noqa: E402
from app.main import app  # noqa: E402
from app.telegram_bot.questionnaire_notifications import deliver_pending_applications_once  # noqa: E402


async def _register_admin(client: AsyncClient) -> tuple[dict, dict[str, str]]:
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"questionnaire-{uuid4()}@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": "Questionnaire Admin",
        },
    )
    assert register.status_code == 201, register.text
    tokens = register.json()
    user_id = UUID(tokens["user"]["id"])
    async with get_session_factory()() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.role = UserRole.SUPERADMIN
        session.add(
            AuthIdentity(
                user_id=user_id,
                provider=AuthProvider.TELEGRAM,
                provider_user_id=str(900000000 + (user_id.int % 99999999)),
            )
        )
        await session.commit()
    return tokens, {"Authorization": f"Bearer {tokens['access_token']}"}


def _question(definition: dict, question_id: str) -> dict:
    return next(item for item in definition["questions"] if item["id"] == question_id)


def _condition_ok(condition: dict | None, answers: dict, house_accepted: bool) -> bool:
    if not condition:
        return True
    operator = condition.get("operator")
    if operator == "house_accepted":
        return house_accepted
    if operator == "all":
        return all(_condition_ok(item, answers, house_accepted) for item in condition.get("conditions", []))
    if operator == "any":
        return any(_condition_ok(item, answers, house_accepted) for item in condition.get("conditions", []))
    answer = answers.get(condition.get("question_id"))
    value = condition.get("value")
    if operator == "eq":
        return answer == value
    if operator == "neq":
        return answer != value
    if operator == "in":
        return isinstance(answer, str) and isinstance(value, list) and answer in value
    if operator == "contains":
        return isinstance(answer, list) and isinstance(value, str) and value in answer
    if operator == "starts_with":
        return isinstance(answer, str) and isinstance(value, str) and answer.startswith(value)
    if operator == "not_contains_any":
        return not isinstance(answer, list) or not isinstance(value, list) or not any(
            item in answer for item in value
        )
    return True


def _valid_object_answers(definition: dict, *, house_accepted: bool) -> dict:
    answers: dict = {}
    for question in definition["questions"]:
        if question["phase"] != "pre_render":
            continue
        if not _condition_ok(question.get("condition"), answers, house_accepted):
            continue
        skip_default = question.get("skip_default")
        if skip_default is not None and _condition_ok(
            question.get("skip_condition"), answers, house_accepted
        ):
            answers[question["id"]] = skip_default
            continue
        if question["kind"] == "number":
            answers[question["id"]] = question.get("min_value") or 1
            continue
        available = [
            option
            for option in question.get("options", [])
            if _condition_ok(
                question.get("option_rules", {}).get(option), answers, house_accepted
            )
        ]
        if question["kind"] == "multi":
            answers[question["id"]] = available[:1]
        else:
            answers[question["id"]] = available[0]

    review = next(
        question
        for question in definition["questions"]
        if question["phase"] == "review"
        and question.get("options")
        and question["options"][0].startswith("Да")
    )
    answers[review["id"]] = review["options"][0]
    return answers


@pytest.mark.asyncio
async def test_questionnaire_catalog_session_and_application_flow() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tokens, headers = await _register_admin(client)
        user_id = UUID(tokens["user"]["id"])

        catalog_response = await client.get("/api/v1/questionnaires", headers=headers)
        assert catalog_response.status_code == 200, catalog_response.text
        catalog = catalog_response.json()
        assert len(catalog["questionnaires"]) == 27

        admin_catalog = await client.get("/api/v1/admin/questionnaires", headers=headers)
        assert admin_catalog.status_code == 200, admin_catalog.text
        assert len(admin_catalog.json()["source_texts"]) == 27

        project_response = await client.post(
            "/api/v1/projects",
            headers=headers,
            json={"name": "Questionnaire integration", "context": {}},
        )
        assert project_response.status_code == 201, project_response.text
        project_id = UUID(project_response.json()["id"])

        house_definition = next(
            item for item in catalog["questionnaires"] if item["key"] == "eskez-doma"
        )
        house_answers = _valid_object_answers(house_definition, house_accepted=False)
        house_lock = {"x": 0.12, "y": 0.10, "width": 0.76, "height": 0.78}
        fake_session = {
            "session_id": str(uuid4()),
            "catalog_version": catalog["version"],
            "selected_objects": ["eskez-doma"],
            "current_object": "zayavka",
            "current_question_id": "20",
            "source_step_completed": True,
            "source_asset_id": None,
            "scene_asset_id": None,
            "answers": {"eskez-doma": house_answers},
            "accepted_objects": ["eskez-doma"],
            "generation_ids": {"eskez-doma": str(uuid4())},
            "edit_question_ids": [],
            "review_comments": {},
            "edit_regions": {},
            "lock_regions": {"eskez-doma": house_lock},
            "region_mode": None,
            "region_object": None,
            "application_submitted": False,
        }
        rejected = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=fake_session,
        )
        assert rejected.status_code == 422, rejected.text

        output_asset = Asset(
            user_id=user_id,
            project_id=project_id,
            type=AssetType.IMAGE,
            purpose=AssetPurpose.GENERATION_OUTPUT,
            original_filename="questionnaire-output.webp",
            mime_type="image/webp",
            size_bytes=128,
            width=1024,
            height=1024,
            storage_path=f"integration/questionnaires/{uuid4()}.webp",
        )
        generation = Generation(
            user_id=user_id,
            project_id=project_id,
            input_asset_id=None,
            type=GenerationType.MASTER_PLAN,
            status=GenerationStatus.COMPLETED,
            prompt="integration questionnaire render",
            credits_charged=0,
        )
        async with get_session_factory()() as session:
            session.add(output_asset)
            await session.flush()
            generation.output_asset_id = output_asset.id
            session.add(generation)
            await session.commit()
            await session.refresh(output_asset)
            await session.refresh(generation)

        design_session = {
            **fake_session,
            "session_id": str(uuid4()),
            "scene_asset_id": str(output_asset.id),
            "generation_ids": {"eskez-doma": str(generation.id)},
        }
        saved = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=design_session,
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["session"]["scene_asset_id"] == str(output_asset.id)

        application_definition = next(
            item for item in catalog["questionnaires"] if item["key"] == "zayavka"
        )
        application_answers = {
            "20": _question(application_definition, "20")["options"][0],
            "21": _question(application_definition, "21")["options"][0],
            "22": _question(application_definition, "22")["options"][0],
            "23": "Иван",
            "24": "+79990000000",
            "25": True,
        }
        submitted_payload = {
            **design_session,
            "current_question_id": None,
            "answers": {
                "eskez-doma": house_answers,
                "zayavka": application_answers,
            },
            "application_submitted": True,
        }
        submitted = await client.post(
            f"/api/v1/projects/{project_id}/questionnaire-application",
            headers=headers,
            json=submitted_payload,
        )
        assert submitted.status_code == 200, submitted.text
        application_id = submitted.json()["application"]["id"]
        assert submitted.json()["application"]["status"] == "new"
        assert submitted.json()["application"]["telegram_delivery_status"] == "pending"

        repeated = await client.post(
            f"/api/v1/projects/{project_id}/questionnaire-application",
            headers=headers,
            json=submitted_payload,
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["application"]["id"] == application_id

        class FakeTelegramApi:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict]] = []

            def call(self, method: str, payload: dict, *, timeout: int = 15):
                self.calls.append((method, payload))
                return {"message_id": len(self.calls)}

        fake_telegram = FakeTelegramApi()
        delivered, failed = await deliver_pending_applications_once(api=fake_telegram)
        assert delivered >= 1
        assert failed == 0
        assert any(
            method == "sendMessage"
            and application_id in payload["text"]
            and payload["chat_id"]
            for method, payload in fake_telegram.calls
        )

        applications = await client.get(
            "/api/v1/admin/questionnaire-applications",
            headers=headers,
        )
        assert applications.status_code == 200, applications.text
        stored_application = next(
            item for item in applications.json() if item["id"] == application_id
        )
        assert stored_application["telegram_delivery_status"] == "sent"
        assert stored_application["telegram_notified_at"] is not None


@pytest.mark.asyncio
async def test_second_accepted_object_requires_masked_composition() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tokens, headers = await _register_admin(client)
        user_id = UUID(tokens["user"]["id"])
        catalog = (await client.get("/api/v1/questionnaires", headers=headers)).json()
        house_definition = next(
            item for item in catalog["questionnaires"] if item["key"] == "eskez-doma"
        )
        bath_definition = next(
            item for item in catalog["questionnaires"] if item["key"] == "banya"
        )
        house_answers = _valid_object_answers(house_definition, house_accepted=False)
        bath_answers = _valid_object_answers(bath_definition, house_accepted=True)

        project_response = await client.post(
            "/api/v1/projects",
            headers=headers,
            json={"name": "Masked questionnaire integration", "context": {}},
        )
        assert project_response.status_code == 201, project_response.text
        project_id = UUID(project_response.json()["id"])

        house_output = Asset(
            user_id=user_id,
            project_id=project_id,
            type=AssetType.IMAGE,
            purpose=AssetPurpose.GENERATION_OUTPUT,
            original_filename="house.png",
            mime_type="image/png",
            size_bytes=128,
            width=1024,
            height=1024,
            storage_path=f"integration/questionnaires/{uuid4()}.png",
        )
        house_generation = Generation(
            user_id=user_id,
            project_id=project_id,
            input_asset_id=None,
            type=GenerationType.MASTER_PLAN,
            status=GenerationStatus.COMPLETED,
            prompt="house",
            credits_charged=0,
        )
        async with get_session_factory()() as session:
            session.add(house_output)
            await session.flush()
            house_generation.output_asset_id = house_output.id
            session.add(house_generation)
            await session.commit()
            await session.refresh(house_output)
            await session.refresh(house_generation)

        house_lock = {"x": 0.15, "y": 0.12, "width": 0.55, "height": 0.66}
        bath_region = {"x": 0.68, "y": 0.30, "width": 0.29, "height": 0.48}
        session_id = str(uuid4())
        house_session = {
            "session_id": session_id,
            "catalog_version": catalog["version"],
            "selected_objects": ["eskez-doma", "banya"],
            "current_object": None,
            "current_question_id": None,
            "source_step_completed": True,
            "source_asset_id": None,
            "scene_asset_id": str(house_output.id),
            "answers": {"eskez-doma": house_answers},
            "accepted_objects": ["eskez-doma"],
            "generation_ids": {"eskez-doma": str(house_generation.id)},
            "edit_question_ids": [],
            "review_comments": {},
            "edit_regions": {},
            "lock_regions": {"eskez-doma": house_lock},
            "region_mode": None,
            "region_object": None,
            "application_submitted": False,
        }
        saved_house = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=house_session,
        )
        assert saved_house.status_code == 200, saved_house.text

        replace_output = Asset(
            user_id=user_id,
            project_id=project_id,
            type=AssetType.IMAGE,
            purpose=AssetPurpose.GENERATION_OUTPUT,
            original_filename="bath-replace.png",
            mime_type="image/png",
            size_bytes=128,
            width=1024,
            height=1024,
            storage_path=f"integration/questionnaires/{uuid4()}.png",
        )
        replace_generation = Generation(
            user_id=user_id,
            project_id=project_id,
            input_asset_id=house_output.id,
            type=GenerationType.MASTER_PLAN,
            status=GenerationStatus.COMPLETED,
            prompt="bath without compositor",
            credits_charged=0,
            composition_mode="replace",
        )
        async with get_session_factory()() as session:
            session.add(replace_output)
            await session.flush()
            replace_generation.output_asset_id = replace_output.id
            session.add(replace_generation)
            await session.commit()
            await session.refresh(replace_output)
            await session.refresh(replace_generation)

        unsafe_payload = {
            **house_session,
            "answers": {
                "eskez-doma": house_answers,
                "banya": bath_answers,
            },
            "scene_asset_id": str(replace_output.id),
            "accepted_objects": ["eskez-doma", "banya"],
            "generation_ids": {
                "eskez-doma": str(house_generation.id),
                "banya": str(replace_generation.id),
            },
            "edit_regions": {"banya": bath_region},
            "lock_regions": {"eskez-doma": house_lock, "banya": bath_region},
        }
        unsafe = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=unsafe_payload,
        )
        assert unsafe.status_code == 422, unsafe.text
        assert "masked composition" in unsafe.json()["detail"]
        forged_payload = {**unsafe_payload, "session_id": str(uuid4())}
        forged = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=forged_payload,
        )
        assert forged.status_code == 422, forged.text
        assert "session id" in forged.json()["detail"].lower()


        masked_output = Asset(
            user_id=user_id,
            project_id=project_id,
            type=AssetType.IMAGE,
            purpose=AssetPurpose.GENERATION_OUTPUT,
            original_filename="bath-masked.png",
            mime_type="image/png",
            size_bytes=128,
            width=1024,
            height=1024,
            storage_path=f"integration/questionnaires/{uuid4()}.png",
        )
        masked_generation = Generation(
            user_id=user_id,
            project_id=project_id,
            input_asset_id=house_output.id,
            type=GenerationType.MASTER_PLAN,
            status=GenerationStatus.COMPLETED,
            prompt="bath with compositor",
            credits_charged=0,
            composition_mode="masked_edit",
            edit_region=bath_region,
            protected_regions=[house_lock],
        )
        async with get_session_factory()() as session:
            session.add(masked_output)
            await session.flush()
            masked_generation.output_asset_id = masked_output.id
            session.add(masked_generation)
            await session.commit()
            await session.refresh(masked_output)
            await session.refresh(masked_generation)

        safe_payload = {
            **unsafe_payload,
            "scene_asset_id": str(masked_output.id),
            "generation_ids": {
                "eskez-doma": str(house_generation.id),
                "banya": str(masked_generation.id),
            },
        }
        safe = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=safe_payload,
        )
        assert safe.status_code == 200, safe.text
        assert safe.json()["session"]["accepted_objects"] == ["eskez-doma", "banya"]
        assert safe.json()["session"]["lock_regions"]["eskez-doma"] == house_lock
