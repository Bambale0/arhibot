import asyncio
import os
from json import loads
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip("set RUN_INTEGRATION_TESTS=1 with a migrated test database", allow_module_level=True)

from app.core.redis import redis_client  # noqa: E402
from app.db.models.assets import Asset  # noqa: E402
from app.db.models.generations import Generation  # noqa: E402
from app.db.models.questionnaires import QuestionnaireApplication  # noqa: E402
from app.db.models.users import AuthIdentity, User  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.domain.assets.enums import AssetPurpose, AssetType  # noqa: E402
from app.domain.generations.enums import GenerationStatus, GenerationType  # noqa: E402
from app.domain.users.enums import AuthProvider, UserRole  # noqa: E402
from app.main import app  # noqa: E402
from app.questionnaires.generation_prompt import build_questionnaire_generation_prompt  # noqa: E402
from app.schemas.questionnaires import DesignSession  # noqa: E402
from app.services.generation_service import GENERATION_QUEUE_KEY  # noqa: E402
from app.services.questionnaire_service import QuestionnaireService  # noqa: E402
from app.telegram_bot.questionnaire_notifications import (  # noqa: E402
    deliver_pending_applications_once,
)


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
    if operator == "floor_option":
        if not isinstance(answer, str) or not isinstance(value, str):
            return False
        floor_answer = answer.lower()
        if value == "Первый этаж":
            return True
        if value == "Второй этаж":
            return not floor_answer.startswith("1 ")
        if value == "Третий этаж":
            return "3" in floor_answer
        if value == "Мансарда":
            return "мансард" in floor_answer
        return False
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
async def test_admin_can_retry_terminal_questionnaire_telegram_delivery_without_duplicates() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tokens, headers = await _register_admin(client)
        user_id = UUID(tokens["user"]["id"])
        project_response = await client.post(
            "/api/v1/projects",
            headers=headers,
            json={"name": "Telegram retry integration", "context": {}},
        )
        assert project_response.status_code == 201, project_response.text
        project_id = UUID(project_response.json()["id"])

        application = QuestionnaireApplication(
            session_id=uuid4(),
            project_id=project_id,
            user_id=user_id,
            catalog_version="2026-09-12.1",
            selected_objects=["lavochka"],
            accepted_objects=["lavochka"],
            answers={},
            scene_asset_id=None,
            status="new",
            telegram_delivery_status="partial",
            telegram_delivery_attempts=17,
            telegram_delivery_error="recipient 999: chat not found",
            telegram_delivery_progress={
                "111": {"photo_sent": True, "chunks_sent": 2},
                "222": {"photo_sent": True, "chunks_sent": 2},
            },
        )
        async with get_session_factory()() as session:
            session.add(application)
            await session.commit()
            await session.refresh(application)
            application_id = application.id

        retried = await client.post(
            f"/api/v1/admin/questionnaire-applications/{application_id}/telegram-retry",
            headers=headers,
        )
        assert retried.status_code == 204, retried.text

        async with get_session_factory()() as session:
            stored = await session.get(QuestionnaireApplication, application_id)
            assert stored is not None
            assert stored.telegram_delivery_status == "pending"
            assert stored.telegram_delivery_attempts == 0
            assert stored.telegram_delivery_error is None
            assert stored.telegram_notified_at is None
            assert stored.telegram_delivery_progress == {
                "111": {"photo_sent": True, "chunks_sent": 2},
                "222": {"photo_sent": True, "chunks_sent": 2},
            }

        duplicate = await client.post(
            f"/api/v1/admin/questionnaire-applications/{application_id}/telegram-retry",
            headers=headers,
        )
        assert duplicate.status_code == 409, duplicate.text
        assert duplicate.json()["type"] == "questionnaire_application_delivery_not_retryable"


@pytest.mark.asyncio
async def test_questionnaire_generation_prompt_is_built_only_on_server_and_hidden_from_response() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        _, headers = await _register_admin(client)
        catalog = (await client.get("/api/v1/questionnaires", headers=headers)).json()
        house_definition = next(
            item for item in catalog["questionnaires"] if item["key"] == "eskez-doma"
        )

        price = await client.put(
            "/api/v1/admin/generation-prices/master_plan",
            headers=headers,
            json={"credits": 7, "is_active": True},
        )
        assert price.status_code == 200, price.text

        started = await client.post(
            "/api/v1/questionnaire-projects",
            headers=headers,
            json={"selected_objects": ["eskez-doma"]},
        )
        assert started.status_code == 201, started.text
        project = started.json()
        project_id = project["id"]
        design_session = project["context"]["design_session"]

        design_session["source_step_completed"] = True
        source_saved = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=design_session,
        )
        assert source_saved.status_code == 200, source_saved.text
        design_session = source_saved.json()["session"]

        answers = _valid_object_answers(house_definition, house_accepted=False)
        review_id = next(
            question["id"]
            for question in house_definition["questions"]
            if question["phase"] == "review"
            and question.get("options")
            and question["options"][0].startswith("Да")
        )
        answers.pop(review_id)
        design_session["answers"] = {"eskez-doma": answers}
        design_session["survey_completed_objects"] = ["eskez-doma"]
        design_session["current_object"] = None
        design_session["current_question_id"] = None
        answers_saved = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=design_session,
        )
        assert answers_saved.status_code == 200, answers_saved.text

        queued = await client.post(
            f"/api/v1/projects/{project_id}/questionnaire-generation",
            headers=headers,
        )
        assert queued.status_code == 202, queued.text
        body = queued.json()
        assert "prompt" not in body
        assert body["type"] == "master_plan"
        assert body["credits_charged"] == 0

        generation_id = UUID(body["id"])
        async with get_session_factory()() as session:
            generation = await session.get(Generation, generation_id)
            assert generation is not None
            assert generation.prompt.startswith("AUROOM_INITIAL_CONCEPT_V1")
            spec_payload = generation.prompt.split("STRUCTURED_SPEC:\n", 1)[1].split(
                "\nFINAL_CHECK:", 1
            )[0]
            spec = loads(spec_payload)
            assert spec["schema"] == "auroom.initial_concept.v1"
            assert spec["task"]["selected_objects_count"] == 1
            assert spec["task"]["objects"][0]["object_key"] == "eskez-doma"
            constraints = {
                item["question"]: item["answer"]
                for item in spec["task"]["objects"][0]["questionnaire_constraints"]
            }
            for question in house_definition["questions"]:
                if (
                    question["phase"] == "pre_render"
                    and question["id"] in answers
                    and _condition_ok(question.get("condition"), answers, False)
                    and answers[question["id"]] not in (None, "", [])
                ):
                    assert str(question["text"]) in constraints

        stored_after_queue = await client.get(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
        )
        assert stored_after_queue.status_code == 200, stored_after_queue.text
        assert (
            stored_after_queue.json()["session"]["initial_generation_id"]
            == str(generation_id)
        )

        duplicate = await client.post(
            f"/api/v1/projects/{project_id}/questionnaire-generation",
            headers=headers,
        )
        assert duplicate.status_code == 422, duplicate.text

        fetched = await client.get(f"/api/v1/generations/{generation_id}", headers=headers)
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["prompt"] == generation.prompt

        questionnaire_fetched = await client.get(
            f"/api/v1/projects/{project_id}/questionnaire-generation/{generation_id}",
            headers=headers,
        )
        assert questionnaire_fetched.status_code == 200, questionnaire_fetched.text
        assert "prompt" not in questionnaire_fetched.json()
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(generation_id))


@pytest.mark.asyncio
async def test_questionnaire_generation_is_atomic_under_concurrent_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        _, headers = await _register_admin(client)
        catalog = (await client.get("/api/v1/questionnaires", headers=headers)).json()
        house_definition = next(
            item for item in catalog["questionnaires"] if item["key"] == "eskez-doma"
        )
        price = await client.put(
            "/api/v1/admin/generation-prices/master_plan",
            headers=headers,
            json={"credits": 7, "is_active": True},
        )
        assert price.status_code == 200, price.text

        started = await client.post(
            "/api/v1/questionnaire-projects",
            headers=headers,
            json={"selected_objects": ["eskez-doma"]},
        )
        project_id = started.json()["id"]
        design_session = started.json()["context"]["design_session"]
        design_session["source_step_completed"] = True
        saved = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=design_session,
        )
        assert saved.status_code == 200, saved.text
        design_session = saved.json()["session"]

        answers = _valid_object_answers(house_definition, house_accepted=False)
        review_id = next(
            question["id"]
            for question in house_definition["questions"]
            if question["phase"] == "review"
            and question.get("options")
            and question["options"][0].startswith("Да")
        )
        answers.pop(review_id)
        design_session["answers"] = {"eskez-doma": answers}
        design_session["survey_completed_objects"] = ["eskez-doma"]
        design_session["current_object"] = None
        design_session["current_question_id"] = None
        saved = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=design_session,
        )
        assert saved.status_code == 200, saved.text

        original = QuestionnaireService.build_generation_request
        release = asyncio.Event()
        ready = 0

        async def synchronized_build(self, user, current_project_id):  # noqa: ANN001
            nonlocal ready
            plan = await original(self, user, current_project_id)
            ready += 1
            if ready == 2:
                release.set()
            await release.wait()
            return plan

        monkeypatch.setattr(
            QuestionnaireService,
            "build_generation_request",
            synchronized_build,
        )
        endpoint = f"/api/v1/projects/{project_id}/questionnaire-generation"
        first, second = await asyncio.gather(
            client.post(endpoint, headers=headers),
            client.post(endpoint, headers=headers),
        )
        statuses = sorted([first.status_code, second.status_code])
        assert statuses == [202, 409], (first.text, second.text)
        success = first if first.status_code == 202 else second
        conflict = second if first.status_code == 202 else first
        assert conflict.json()["type"] == "questionnaire_generation_state_changed"

        generation_id = success.json()["id"]
        stored = await client.get(
            f"/api/v1/projects/{project_id}/questionnaire-session", headers=headers
        )
        assert stored.json()["session"]["initial_generation_id"] == generation_id
        listed = await client.get(
            f"/api/v1/generations?project_id={project_id}", headers=headers
        )
        assert listed.status_code == 200, listed.text
        assert [item["id"] for item in listed.json()["items"]] == [generation_id]
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, generation_id)


@pytest.mark.asyncio
async def test_initial_concept_refinement_updates_scene_generation_chain() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tokens, headers = await _register_admin(client)
        user_id = UUID(tokens["user"]["id"])
        catalog = (await client.get("/api/v1/questionnaires", headers=headers)).json()
        definition = next(
            item for item in catalog["questionnaires"] if item["key"] == "lavochka"
        )

        price = await client.put(
            "/api/v1/admin/generation-prices/master_plan",
            headers=headers,
            json={"credits": 3, "is_active": True},
        )
        assert price.status_code == 200, price.text

        started = await client.post(
            "/api/v1/questionnaire-projects",
            headers=headers,
            json={"selected_objects": ["lavochka"]},
        )
        assert started.status_code == 201, started.text
        project_id = started.json()["id"]
        session = started.json()["context"]["design_session"]
        session["source_step_completed"] = True
        saved = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=session,
        )
        assert saved.status_code == 200, saved.text
        session = saved.json()["session"]

        answers = _valid_object_answers(definition, house_accepted=False)
        review = next(
            question
            for question in definition["questions"]
            if question["phase"] == "review"
            and question.get("options")
            and question["options"][0].startswith("Да")
        )
        answers.pop(review["id"])
        session["answers"] = {"lavochka": answers}
        session["survey_completed_objects"] = ["lavochka"]
        session["current_object"] = None
        session["current_question_id"] = None
        saved = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=session,
        )
        assert saved.status_code == 200, saved.text

        initial = await client.post(
            f"/api/v1/projects/{project_id}/questionnaire-generation",
            headers=headers,
        )
        assert initial.status_code == 202, initial.text
        initial_id = UUID(initial.json()["id"])
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(initial_id))

        initial_asset = Asset(
            user_id=user_id,
            project_id=UUID(project_id),
            type=AssetType.IMAGE,
            purpose=AssetPurpose.GENERATION_OUTPUT,
            original_filename="initial.webp",
            mime_type="image/webp",
            size_bytes=128,
            width=1280,
            height=720,
            storage_path=f"integration/questionnaires/{uuid4()}.webp",
        )
        async with get_session_factory()() as db:
            db.add(initial_asset)
            await db.flush()
            generation = await db.get(Generation, initial_id)
            assert generation is not None
            generation.status = GenerationStatus.COMPLETED
            generation.output_asset_id = initial_asset.id
            await db.commit()
            await db.refresh(initial_asset)

        accepted = await client.post(
            f"/api/v1/projects/{project_id}/questionnaire-initial-accept",
            headers=headers,
        )
        assert accepted.status_code == 200, accepted.text
        session = accepted.json()["session"]
        assert session["scene_generation_id"] == str(initial_id)
        assert session["scene_asset_id"] == str(initial_asset.id)

        session["current_object"] = "lavochka"
        session["region_mode"] = "edit"
        session["region_object"] = "lavochka"
        started_refinement = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=session,
        )
        assert started_refinement.status_code == 200, started_refinement.text
        session = started_refinement.json()["session"]

        region = {"x": 0.12, "y": 0.18, "width": 0.35, "height": 0.42}
        session["edit_regions"]["lavochka"] = region
        session["review_comments"]["lavochka"] = "Перенести лавочку левее."
        session["region_mode"] = None
        session["region_object"] = None
        region_saved = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=session,
        )
        assert region_saved.status_code == 200, region_saved.text

        refinement = await client.post(
            f"/api/v1/projects/{project_id}/questionnaire-generation",
            headers=headers,
        )
        assert refinement.status_code == 202, refinement.text
        refinement_id = UUID(refinement.json()["id"])
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(refinement_id))

        refined_asset = Asset(
            user_id=user_id,
            project_id=UUID(project_id),
            type=AssetType.IMAGE,
            purpose=AssetPurpose.GENERATION_OUTPUT,
            original_filename="refined.webp",
            mime_type="image/webp",
            size_bytes=128,
            width=1280,
            height=720,
            storage_path=f"integration/questionnaires/{uuid4()}.webp",
        )
        async with get_session_factory()() as db:
            db.add(refined_asset)
            await db.flush()
            generation = await db.get(Generation, refinement_id)
            assert generation is not None
            assert generation.composition_mode == "masked_edit"
            assert generation.input_asset_id == initial_asset.id
            generation.status = GenerationStatus.COMPLETED
            generation.output_asset_id = refined_asset.id
            await db.commit()
            await db.refresh(refined_asset)

        current = await client.get(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
        )
        session = current.json()["session"]
        session["answers"]["lavochka"][review["id"]] = review["options"][0]
        session["current_question_id"] = review["id"]
        reviewed = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=session,
        )
        assert reviewed.status_code == 200, reviewed.text
        session = reviewed.json()["session"]

        session["scene_asset_id"] = str(refined_asset.id)
        session["scene_generation_id"] = str(refinement_id)
        session["lock_regions"]["lavochka"] = region
        session["current_object"] = None
        session["current_question_id"] = None
        finalized = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=session,
        )
        assert finalized.status_code == 200, finalized.text
        session = finalized.json()["session"]
        assert session["scene_generation_id"] == str(refinement_id)
        assert session["scene_asset_id"] == str(refined_asset.id)

        session["current_object"] = "zayavka"
        session["current_question_id"] = "20"
        ordinary_save = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=session,
        )
        assert ordinary_save.status_code == 200, ordinary_save.text


@pytest.mark.asyncio
async def test_accepted_object_removal_is_a_paid_masked_iteration() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tokens, headers = await _register_admin(client)
        user_id = UUID(tokens["user"]["id"])
        catalog = (await client.get("/api/v1/questionnaires", headers=headers)).json()
        object_keys = ["lavochka", "kacheli"]
        definitions = {
            key: next(
                item for item in catalog["questionnaires"] if item["key"] == key
            )
            for key in object_keys
        }

        price = await client.put(
            "/api/v1/admin/generation-prices/master_plan",
            headers=headers,
            json={"credits": 3, "is_active": True},
        )
        assert price.status_code == 200, price.text

        started = await client.post(
            "/api/v1/questionnaire-projects",
            headers=headers,
            json={"selected_objects": object_keys},
        )
        assert started.status_code == 201, started.text
        project_id = started.json()["id"]
        session = started.json()["context"]["design_session"]
        ordered_keys = session["selected_objects"]
        assert set(ordered_keys) == set(object_keys)

        session["source_step_completed"] = True
        source_saved = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=session,
        )
        assert source_saved.status_code == 200, source_saved.text
        session = source_saved.json()["session"]

        initial_answers: dict[str, dict] = {}
        for key in ordered_keys:
            answers = _valid_object_answers(definitions[key], house_accepted=False)
            review = next(
                question
                for question in definitions[key]["questions"]
                if question["phase"] == "review"
                and question.get("options")
                and question["options"][0].startswith("Да")
            )
            answers.pop(review["id"])
            initial_answers[key] = answers
        session["answers"] = initial_answers
        session["survey_completed_objects"] = list(ordered_keys)
        session["current_object"] = None
        session["current_question_id"] = None

        answers_saved = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=session,
        )
        assert answers_saved.status_code == 200, answers_saved.text

        initial = await client.post(
            f"/api/v1/projects/{project_id}/questionnaire-generation",
            headers=headers,
        )
        assert initial.status_code == 202, initial.text
        initial_id = UUID(initial.json()["id"])
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(initial_id))

        initial_asset = Asset(
            user_id=user_id,
            project_id=UUID(project_id),
            type=AssetType.IMAGE,
            purpose=AssetPurpose.GENERATION_OUTPUT,
            original_filename="removal-initial.webp",
            mime_type="image/webp",
            size_bytes=128,
            width=1280,
            height=720,
            storage_path=f"integration/questionnaires/{uuid4()}.webp",
        )
        async with get_session_factory()() as db:
            db.add(initial_asset)
            await db.flush()
            generation = await db.get(Generation, initial_id)
            assert generation is not None
            generation.status = GenerationStatus.COMPLETED
            generation.output_asset_id = initial_asset.id
            await db.commit()
            await db.refresh(initial_asset)

        accepted = await client.post(
            f"/api/v1/projects/{project_id}/questionnaire-initial-accept",
            headers=headers,
        )
        assert accepted.status_code == 200, accepted.text
        session = accepted.json()["session"]
        assert set(session["accepted_objects"]) == set(object_keys)
        assert session["removed_objects"] == []

        remove_key = "lavochka"
        remaining_key = "kacheli"
        started_removal = await client.post(
            f"/api/v1/projects/{project_id}/questionnaire-object-removal",
            headers=headers,
            json={"object_key": remove_key},
        )
        assert started_removal.status_code == 200, started_removal.text
        session = started_removal.json()["session"]
        assert session["pending_removal_object"] == remove_key
        assert session["current_object"] == remove_key
        assert session["region_mode"] == "edit"

        region = {"x": 0.08, "y": 0.20, "width": 0.32, "height": 0.46}
        session["edit_regions"][remove_key] = region
        session["region_mode"] = None
        session["region_object"] = None
        region_saved = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=session,
        )
        assert region_saved.status_code == 200, region_saved.text

        removal = await client.post(
            f"/api/v1/projects/{project_id}/questionnaire-generation",
            headers=headers,
        )
        assert removal.status_code == 202, removal.text
        removal_id = UUID(removal.json()["id"])
        await redis_client.lrem(GENERATION_QUEUE_KEY, 0, str(removal_id))

        removal_asset = Asset(
            user_id=user_id,
            project_id=UUID(project_id),
            type=AssetType.IMAGE,
            purpose=AssetPurpose.GENERATION_OUTPUT,
            original_filename="removal-result.webp",
            mime_type="image/webp",
            size_bytes=128,
            width=1280,
            height=720,
            storage_path=f"integration/questionnaires/{uuid4()}.webp",
        )
        async with get_session_factory()() as db:
            db.add(removal_asset)
            await db.flush()
            generation = await db.get(Generation, removal_id)
            assert generation is not None
            assert generation.type == GenerationType.MASTER_PLAN
            assert generation.composition_mode == "masked_edit"
            assert generation.input_asset_id == initial_asset.id
            assert generation.edit_region == region
            assert '"operation":"remove_object"' in generation.prompt
            generation.status = GenerationStatus.COMPLETED
            generation.output_asset_id = removal_asset.id
            await db.commit()
            await db.refresh(removal_asset)

        removed = await client.post(
            f"/api/v1/projects/{project_id}/questionnaire-object-removal/accept",
            headers=headers,
        )
        assert removed.status_code == 200, removed.text
        session = removed.json()["session"]
        assert session["accepted_objects"] == [remaining_key]
        assert session["removed_objects"] == [remove_key]
        assert session["pending_removal_object"] is None
        assert session["scene_asset_id"] == str(removal_asset.id)
        assert session["scene_generation_id"] == str(removal_id)
        assert session["current_object"] is None
        assert remove_key not in session["lock_regions"]
        assert remove_key not in session["edit_regions"]

        session["current_object"] = "zayavka"
        session["current_question_id"] = "20"
        ordinary_save = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=session,
        )
        assert ordinary_save.status_code == 200, ordinary_save.text


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
        canonical_house_prompt = build_questionnaire_generation_prompt(
            house_definition,
            DesignSession.model_validate(fake_session),
            accepted_before=[],
            input_asset_present=False,
        )
        generation = Generation(
            user_id=user_id,
            project_id=project_id,
            input_asset_id=None,
            type=GenerationType.MASTER_PLAN,
            status=GenerationStatus.COMPLETED,
            prompt=canonical_house_prompt,
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
        delivered, failed = await deliver_pending_applications_once(
            api=fake_telegram,
            webapp_url="https://app.example.test/",
        )
        assert delivered >= 1
        assert failed == 0
        assert any(
            method == "sendMessage"
            and application_id in payload["text"]
            and payload["chat_id"]
            for method, payload in fake_telegram.calls
        )
        assert any(
            method == "sendMessage"
            and "Архитектурный бриф" in payload["text"]
            for method, payload in fake_telegram.calls
        )
        joined_admin_text = "\n".join(
            payload["text"]
            for method, payload in fake_telegram.calls
            if method == "sendMessage"
        )
        assert "Контакт из заявки: +79990000000" in joined_admin_text
        assert "E-mail аккаунта:" in joined_admin_text
        assert "Telegram ID:" in joined_admin_text
        assert f"User ID: {user_id}" in joined_admin_text
        assert f"Проект ID: {project_id}" in joined_admin_text
        assert f"Финальная работа generation: {generation.id}" in joined_admin_text
        photo_payload = next(
            payload
            for method, payload in fake_telegram.calls
            if method == "sendPhoto" and application_id in payload["caption"]
        )
        assert photo_payload["photo"]
        keyboard = photo_payload["reply_markup"]["inline_keyboard"]
        assert keyboard[0][0]["text"] == "Работа / проект"
        assert f"project={project_id}" in keyboard[0][0]["web_app"]["url"]
        assert f"generation={generation.id}" in keyboard[0][0]["web_app"]["url"]
        assert keyboard[1][0]["text"] == "Заявка в админке"
        assert f"application={application_id}" in keyboard[1][0]["web_app"]["url"]
        assert keyboard[2][0]["text"] == "Профиль клиента"
        assert f"user={user_id}" in keyboard[2][0]["web_app"]["url"]

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
        assert stored_application["project_name"]
        assert stored_application["scene_asset_url"]
        assert stored_application["application_contact"] == "+79990000000"
        assert stored_application["telegram_user_id"]
        assert stored_application["user_email"].endswith("@example.com")
        assert stored_application["final_generation_id"] == str(generation.id)
        house_brief = next(
            item for item in stored_application["brief"] if item["key"] == "eskez-doma"
        )
        assert house_brief["accepted"] is True
        assert house_brief["answers"]


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
        house_prompt_session = DesignSession(
            catalog_version=catalog["version"],
            selected_objects=["eskez-doma", "banya"],
            source_step_completed=True,
            answers={"eskez-doma": house_answers},
        )
        house_generation = Generation(
            user_id=user_id,
            project_id=project_id,
            input_asset_id=None,
            type=GenerationType.MASTER_PLAN,
            status=GenerationStatus.COMPLETED,
            prompt=build_questionnaire_generation_prompt(
                house_definition,
                house_prompt_session,
                accepted_before=[],
                input_asset_present=False,
            ),
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

        bath_prompt_session = DesignSession.model_validate(
            {
                **house_session,
                "answers": {
                    "eskez-doma": house_answers,
                    "banya": bath_answers,
                },
                "edit_regions": {"banya": bath_region},
            }
        )
        canonical_bath_prompt = build_questionnaire_generation_prompt(
            bath_definition,
            bath_prompt_session,
            accepted_before=["eskez-doma"],
            input_asset_present=True,
        )

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
            prompt=canonical_bath_prompt,
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

        bad_prompt_output = Asset(
            user_id=user_id,
            project_id=project_id,
            type=AssetType.IMAGE,
            purpose=AssetPurpose.GENERATION_OUTPUT,
            original_filename="bath-bad-prompt.png",
            mime_type="image/png",
            size_bytes=128,
            width=1024,
            height=1024,
            storage_path=f"integration/questionnaires/{uuid4()}.png",
        )
        bad_prompt_generation = Generation(
            user_id=user_id,
            project_id=project_id,
            input_asset_id=house_output.id,
            type=GenerationType.MASTER_PLAN,
            status=GenerationStatus.COMPLETED,
            prompt="forged questionnaire prompt",
            credits_charged=0,
            composition_mode="masked_edit",
            edit_region=bath_region,
            protected_regions=[house_lock],
        )
        wrong_type_output = Asset(
            user_id=user_id,
            project_id=project_id,
            type=AssetType.IMAGE,
            purpose=AssetPurpose.GENERATION_OUTPUT,
            original_filename="bath-wrong-type.png",
            mime_type="image/png",
            size_bytes=128,
            width=1024,
            height=1024,
            storage_path=f"integration/questionnaires/{uuid4()}.png",
        )
        wrong_type_generation = Generation(
            user_id=user_id,
            project_id=project_id,
            input_asset_id=house_output.id,
            type=GenerationType.FACADE,
            status=GenerationStatus.COMPLETED,
            prompt=canonical_bath_prompt,
            credits_charged=0,
            composition_mode="masked_edit",
            edit_region=bath_region,
            protected_regions=[house_lock],
        )
        async with get_session_factory()() as session:
            session.add_all([bad_prompt_output, wrong_type_output])
            await session.flush()
            bad_prompt_generation.output_asset_id = bad_prompt_output.id
            wrong_type_generation.output_asset_id = wrong_type_output.id
            session.add_all([bad_prompt_generation, wrong_type_generation])
            await session.commit()
            await session.refresh(bad_prompt_generation)
            await session.refresh(wrong_type_generation)

        bad_prompt_payload = {
            **unsafe_payload,
            "scene_asset_id": str(bad_prompt_output.id),
            "generation_ids": {
                "eskez-doma": str(house_generation.id),
                "banya": str(bad_prompt_generation.id),
            },
        }
        bad_prompt_response = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=bad_prompt_payload,
        )
        assert bad_prompt_response.status_code == 422, bad_prompt_response.text
        assert "prompt" in bad_prompt_response.json()["detail"].lower()

        wrong_type_payload = {
            **unsafe_payload,
            "scene_asset_id": str(wrong_type_output.id),
            "generation_ids": {
                "eskez-doma": str(house_generation.id),
                "banya": str(wrong_type_generation.id),
            },
        }
        wrong_type_response = await client.put(
            f"/api/v1/projects/{project_id}/questionnaire-session",
            headers=headers,
            json=wrong_type_payload,
        )
        assert wrong_type_response.status_code == 422, wrong_type_response.text
        assert "master_plan" in wrong_type_response.json()["detail"]

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
            prompt=canonical_bath_prompt,
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
