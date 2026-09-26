from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.schemas.questionnaires import DesignSession
from app.services.questionnaire_service import QuestionnaireService


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["add", "remove"])
async def test_initial_concept_inferred_locks_do_not_block_selected_edit(operation):
    service = QuestionnaireService(AsyncMock())
    key = "banya" if operation == "add" else "basseyn"
    state = DesignSession(
        catalog_version="test",
        selected_objects=["eskez-doma", key],
        initial_concept_mode=True,
        initial_concept_accepted=True,
        initial_generation_id=uuid4(),
        source_step_completed=True,
        scene_asset_id=uuid4(),
        current_object=key,
        accepted_objects=["eskez-doma"] if operation == "add" else ["eskez-doma", key],
        pending_removal_object=key if operation == "remove" else None,
        edit_regions={key: {"x": 0.3, "y": 0.3, "width": 0.2, "height": 0.2}},
        lock_regions={"eskez-doma": {"x": 0.12, "y": 0.1, "width": 0.76, "height": 0.78}},
    )
    project = SimpleNamespace(context={"design_session": state.model_dump(mode="json")})
    service.catalog_for_version = AsyncMock(
        return_value={
            "questionnaires": [{"key": key, "title": key, "questions": []}],
        }
    )
    with patch(
        "app.services.questionnaire_service.ProjectService.get_owned_model",
        AsyncMock(return_value=project),
    ):
        payload, _, _ = await service.build_generation_request(SimpleNamespace(id=uuid4()), uuid4())
    assert payload.composition_mode == "masked_edit"
    assert payload.protected_regions == []
    assert payload.edit_region == state.edit_regions[key]
    if operation == "remove":
        assert payload.edit_policy["intent"] == "object_removal"
        assert payload.edit_policy["preserve_building_geometry"] is False


@pytest.mark.asyncio
async def test_real_protected_region_returns_actionable_error_before_creation():
    service = QuestionnaireService(AsyncMock())
    lock = {"x": 0.12, "y": 0.1, "width": 0.76, "height": 0.78}
    state = DesignSession(
        catalog_version="test",
        selected_objects=["eskez-doma", "banya"],
        initial_concept_mode=True,
        initial_concept_accepted=True,
        initial_generation_id=uuid4(),
        source_step_completed=True,
        scene_asset_id=uuid4(),
        current_object="banya",
        accepted_objects=["eskez-doma"],
        edit_regions={
            "eskez-doma": lock,
            "banya": {"x": 0.3, "y": 0.3, "width": 0.2, "height": 0.2},
        },
        lock_regions={"eskez-doma": lock},
    )
    project = SimpleNamespace(context={"design_session": state.model_dump(mode="json")})
    service.catalog_for_version = AsyncMock(
        return_value={
            "questionnaires": [{"key": "banya", "title": "Баня", "questions": []}],
        }
    )
    with patch(
        "app.services.questionnaire_service.ProjectService.get_owned_model",
        AsyncMock(return_value=project),
    ):
        with pytest.raises(AppError) as caught:
            await service.build_generation_request(SimpleNamespace(id=uuid4()), uuid4())
    assert caught.value.status == 422
    assert caught.value.type == "questionnaire_edit_region_blocked"


def test_generation_binding_atomically_leaves_region_picker():
    state = DesignSession(
        catalog_version="test",
        selected_objects=["banya"],
        current_object="banya",
        region_mode="edit",
        region_object="banya",
    )
    project = SimpleNamespace(context={"design_session": state.model_dump(mode="json")})
    generation_id = uuid4()
    QuestionnaireService.bind_generation_before_commit(
        project,
        expected_session=state,
        object_key="banya",
        generation_id=generation_id,
    )
    bound = DesignSession.model_validate(project.context["design_session"])
    assert bound.generation_ids["banya"] == generation_id
    assert bound.region_mode is None
    assert bound.region_object is None


def test_stale_client_cannot_replace_server_bound_accepted_edit():
    state = DesignSession(
        catalog_version="test",
        selected_objects=["banya"],
        initial_concept_mode=True,
        initial_concept_accepted=True,
        initial_generation_id=uuid4(),
        current_object="banya",
        accepted_objects=["banya"],
        generation_ids={"banya": uuid4()},
    )
    stale = state.model_copy(update={"generation_ids": {"banya": uuid4()}})
    with pytest.raises(AppError):
        QuestionnaireService._validate_accepted_object_locks(state, stale)


def test_initial_protection_uses_selected_region_instead_of_old_guessed_lock():
    from app.questionnaires.regions import protected_object_regions

    selected = {"x": 0.1, "y": 0.1, "width": 0.15, "height": 0.15}
    state = DesignSession(
        catalog_version="test",
        selected_objects=["banya"],
        initial_concept_mode=True,
        edit_regions={"banya": selected},
        lock_regions={"banya": {"x": 0, "y": 0, "width": 1, "height": 1}},
    )
    assert [region.model_dump() for region in protected_object_regions(state, ["banya"])] == [
        selected
    ]
    legacy = state.model_copy(update={"initial_concept_mode": False})
    assert protected_object_regions(legacy, ["banya"]) == [state.lock_regions["banya"]]


def test_internal_prompt_overflow_is_an_actionable_error():
    from app.schemas.generations import QUESTIONNAIRE_PROMPT_MAX_LENGTH

    with pytest.raises(AppError) as caught:
        QuestionnaireService._validate_prompt_length("x" * (QUESTIONNAIRE_PROMPT_MAX_LENGTH + 1))
    assert caught.value.status == 422
    assert caught.value.type == "questionnaire_prompt_too_long"


@pytest.mark.asyncio
@pytest.mark.parametrize("longest", [False, True])
async def test_full_catalog_fits_internal_generation_request_budget(longest):
    from app.questionnaires.catalog import build_catalog
    from app.questionnaires.generation_prompt import condition_ok, question_is_active
    from app.schemas.generations import QUESTIONNAIRE_PROMPT_MAX_LENGTH

    catalog = build_catalog()
    service = QuestionnaireService(AsyncMock())
    keys = [key for section in catalog["sections"] for key in section["object_keys"]]
    answers = {}
    for definition in catalog["questionnaires"]:
        key = definition["key"]
        if key not in keys:
            continue
        values = {}
        for question in definition["questions"]:
            if question["phase"] != "pre_render" or not question_is_active(
                key, question, values, True, keys
            ):
                continue
            options = [
                option
                for option in question.get("options", [])
                if option != "Свой вариант"
                and condition_ok(
                    (question.get("option_rules") or {}).get(option), values, True, keys
                )
            ]
            if longest:
                options.sort(key=len, reverse=True)
            if question["kind"] == "number":
                desired = 200 if key == "eskez-doma" and question["id"] == "3" else 5
                candidates = [
                    max(
                        question.get("min_value") or 0,
                        min(question.get("max_value") or 200, desired),
                    )
                ]
            elif question["kind"] == "multi":
                candidates = (
                    [options[: question.get("max_selections") or len(options)]]
                    if longest
                    else [[option] for option in options]
                )
            else:
                candidates = options or ["Стандартный вариант"]
            for value in candidates:
                try:
                    service._validate_answer(question, value, values, True)
                except AppError:
                    continue
                values[question["id"]] = value
                break
            else:
                raise AssertionError((key, question["id"]))
        answers[key] = values
    state = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=keys,
        plot_area_sotkas=10,
        initial_concept_mode=True,
        source_step_completed=True,
        survey_completed_objects=keys,
        answers=answers,
    )
    service._validate(state, catalog, allow_submitted=False)
    service.catalog_for_version = AsyncMock(return_value=catalog)
    project = SimpleNamespace(context={"design_session": state.model_dump(mode="json")})
    with patch(
        "app.services.questionnaire_service.ProjectService.get_owned_model",
        AsyncMock(return_value=project),
    ):
        payload, _, key = await service.build_generation_request(
            SimpleNamespace(id=uuid4()), uuid4()
        )
    assert key == "__initial__"
    assert len(keys) == 26
    assert 16_000 < len(payload.prompt) < QUESTIONNAIRE_PROMPT_MAX_LENGTH
