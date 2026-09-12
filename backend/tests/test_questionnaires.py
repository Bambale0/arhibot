from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.errors import AppError
from app.questionnaires.catalog import CATALOG_VERSION, _load_sources, build_catalog
from app.schemas.questionnaires import DesignSession, QuestionnaireCatalogResponse
from app.services.questionnaire_service import QuestionnaireService


def _definition(key: str) -> dict:
    return next(item for item in build_catalog()["questionnaires"] if item["key"] == key)


def _question(key: str, question_id: str) -> dict:
    return next(item for item in _definition(key)["questions"] if item["id"] == question_id)


def test_questionnaire_catalog_matches_source_bundle() -> None:
    catalog = QuestionnaireCatalogResponse.model_validate(build_catalog())
    sources = _load_sources()
    assert catalog.version == "2026-09-12.1"
    assert CATALOG_VERSION == catalog.version
    assert len(catalog.sections) == 6
    assert len(catalog.questionnaires) == 27
    assert len(sources) == 27
    assert set(sources) == {item.key for item in catalog.questionnaires}
    for definition in catalog.questionnaires:
        assert sources[definition.key]["filename"] == definition.source_file
        assert sources[definition.key]["text"].strip()
    assert catalog.sections[0].object_keys == ["eskez-doma"]
    assert catalog.sections[-1].object_keys == ["dorozhki", "gazon", "prud", "podsvetka", "podpornye"]
    assert catalog.application_key == "zayavka"


def test_legacy_catalog_builder_preserves_historical_copy_for_revision_archive() -> None:
    legacy = build_catalog(user_facing=False, version="2026-09-09.2")
    house = next(item for item in legacy["questionnaires"] if item["key"] == "eskez-doma")
    garage_place = next(item for item in house["questions"] if item["id"] == "6а")
    assert legacy["version"] == "2026-09-09.2"
    assert garage_place["text"] == "Где гараж?  (если «да»)"


def test_house_questionnaire_keeps_exact_branches_defaults_and_limits() -> None:
    style = _question("eskez-doma", "1")
    garage = _question("eskez-doma", "6")
    garage_place = _question("eskez-doma", "6а")
    roof = _question("eskez-doma", "7")
    facade = _question("eskez-doma", "8")
    glazing = _question("eskez-doma", "9")
    lighting = _question("eskez-doma", "14")
    review = _question("eskez-doma", "15")
    edit = _question("eskez-doma", "15б")
    assert style["options"] == ["Современный минимализм", "Барнхаус", "Скандинавский", "Шале", "Фахверк", "Классика", "Хай-тек", "Средиземноморский"]
    assert garage["options"] == ["Да", "Нет"]
    assert garage_place["condition"] == {"question_id": "6", "operator": "eq", "value": "Да"}
    assert roof["option_rules"]["Плоская"]["value"] == ["Современный минимализм", "Средиземноморский", "Хай-тек"]
    assert facade["kind"] == "multi" and facade["max_selections"] == 3
    assert glazing["skip_default"] == "Стандартные окна"
    assert lighting["skip_default"] == "Дневной свет"
    assert review["phase"] == "review"
    assert edit["field_hint"] == "Свой комментарий"
    assert edit["edit_targets"]["Размер и этажность"] == ["3", "4"]
    assert edit["edit_targets"]["Гараж, навес, пристрой"] == ["6", "6а", "6б", "6в"]
    assert _question("eskez-doma", "6а")["text"] == "Где гараж?"
    assert _question("eskez-doma", "6б")["text"] == "Какой именно?"
    assert _question("eskez-doma", "13а")["text"] == "Какой балкон?"
    assert _question("eskez-doma", "6а")["condition"] == {"question_id": "6", "operator": "eq", "value": "Да"}
    assert _question("eskez-doma", "6б")["condition"] == {"question_id": "6а", "operator": "eq", "value": "Не в доме"}
    assert _question("eskez-doma", "13а")["condition"] == {"question_id": "13", "operator": "contains", "value": "Балкон"}


def test_each_object_ends_with_review_and_application_is_separate() -> None:
    for definition in build_catalog()["questionnaires"]:
        if definition["key"] == "zayavka":
            continue
        reviews = [q for q in definition["questions"] if q["phase"] == "review"]
        assert reviews, definition["key"]
        assert reviews[0]["options"][0].startswith("Да")
        assert reviews[0]["options"][1].startswith("Нет")
    application = _definition("zayavka")
    assert [q["id"] for q in application["questions"]] == ["20", "21", "22", "23", "24", "25"]
    contact = _question("zayavka", "24")
    assert contact["text"] == "Оставьте телефон или @username Telegram"
    assert contact["placeholder"] == "+7 999 123-45-67 или @username"
    assert _question("zayavka", "25")["kind"] == "consent"


def test_skip_defaults_keep_source_semantics_after_schema_validation() -> None:
    catalog = QuestionnaireCatalogResponse.model_validate(build_catalog())
    for definition in catalog.questionnaires:
        for question in definition.questions:
            if question.skip_default is None:
                continue
            assert isinstance(question.skip_default, (str, list))
            if isinstance(question.skip_default, list):
                assert all(isinstance(item, str) for item in question.skip_default)


def test_design_session_is_versioned_and_does_not_require_a_site_photo() -> None:
    first = DesignSession(catalog_version=CATALOG_VERSION, selected_objects=["eskez-doma", "banya"], source_step_completed=True, source_asset_id=None)
    second = DesignSession(catalog_version=CATALOG_VERSION, selected_objects=["eskez-doma"])
    assert first.source_step_completed is True
    assert first.source_asset_id is None
    assert first.selected_objects == ["eskez-doma", "banya"]
    assert first.session_id != second.session_id


def test_like_house_option_is_available_only_after_house_is_accepted() -> None:
    style = _question("banya", "1")
    assert style["option_rules"]["Как у дома"] == {"operator": "house_accepted"}

    with pytest.raises(ValidationError, match="Как у дома"):
        DesignSession(
            catalog_version=CATALOG_VERSION,
            selected_objects=["banya"],
            answers={"banya": {"1": "Как у дома"}},
        )

    session = DesignSession(
        catalog_version=CATALOG_VERSION,
        selected_objects=["eskez-doma", "banya"],
        accepted_objects=["eskez-doma"],
        answers={"banya": {"1": "Как у дома"}},
    )
    assert session.answers["banya"]["1"] == "Как у дома"


def test_facade_skip_exists_only_for_inherited_house_style() -> None:
    for object_key, question_id in {
        "gostevoy": "8",
        "banya": "9",
        "garazh": "6",
        "letnyaya-kuhnya": "7",
        "hozblok": "5",
    }.items():
        facade = _question(object_key, question_id)
        assert facade["skip_default"] == "отделка дома"
        assert facade["skip_condition"] == {
            "question_id": "1",
            "operator": "eq",
            "value": "Как у дома",
        }
    assert _question("naves", "5")["skip_default"] is None
    assert _question("zabor", "4")["skip_default"] is None


def test_accepted_objects_and_site_source_are_immutable_within_session() -> None:
    session_id = uuid4()
    source_id = uuid4()
    scene_id = uuid4()
    generation_id = uuid4()
    previous = DesignSession(
        session_id=session_id,
        catalog_version=CATALOG_VERSION,
        selected_objects=["eskez-doma", "banya"],
        source_step_completed=True,
        source_asset_id=source_id,
        scene_asset_id=scene_id,
        answers={"eskez-doma": {"1": "Барнхаус"}},
        accepted_objects=["eskez-doma"],
        generation_ids={"eskez-doma": generation_id},
    )
    QuestionnaireService._validate_accepted_object_locks(previous, previous.model_copy(deep=True))

    changed_answer = previous.model_copy(deep=True)
    changed_answer.answers["eskez-doma"]["1"] = "Шале"
    with pytest.raises(AppError) as exc:
        QuestionnaireService._validate_accepted_object_locks(previous, changed_answer)
    assert "cannot change answers" in exc.value.detail

    changed_source = previous.model_copy(update={"source_asset_id": uuid4()})
    with pytest.raises(AppError) as exc:
        QuestionnaireService._validate_accepted_object_locks(previous, changed_source)
    assert "site-photo choice is fixed" in exc.value.detail

    changed_selection = previous.model_copy(update={"selected_objects": ["eskez-doma"]})
    with pytest.raises(AppError) as exc:
        QuestionnaireService._validate_accepted_object_locks(previous, changed_selection)
    assert "Selected questionnaire objects are fixed" in exc.value.detail

    removed = previous.model_copy(update={"accepted_objects": []})
    with pytest.raises(AppError) as exc:
        QuestionnaireService._validate_accepted_object_locks(previous, removed)
    assert "Accepted objects are immutable" in exc.value.detail


def test_server_accepts_only_explicit_skip_defaults() -> None:
    service = QuestionnaireService(None)  # validation is pure; repositories are not used here

    guest_facade = _question("gostevoy", "8")
    service._validate_answer(
        guest_facade,
        "отделка дома",
        {"1": "Как у дома"},
        True,
    )
    with pytest.raises(AppError) as exc:
        service._validate_answer(
            guest_facade,
            "отделка дома",
            {"1": "Барнхаус"},
            True,
        )
    assert "cannot be skipped" in exc.value.detail

    non_skippable_multi = _question("zabor", "4")
    with pytest.raises(AppError) as exc:
        service._validate_answer(non_skippable_multi, [], {}, False)
    assert "explicit skip" in exc.value.detail

    house_refinement = _question("eskez-doma", "15б")
    service._validate_answer(
        house_refinement,
        [],
        {},
        False,
        allow_empty_multi=True,
    )


def test_server_rejects_options_hidden_by_questionnaire_rules() -> None:
    service = QuestionnaireService(None)

    roof = _question("eskez-doma", "7")
    with pytest.raises(AppError) as exc:
        service._validate_answer(roof, "Плоская", {"1": "Барнхаус"}, False)
    assert "inactive" in exc.value.detail
    service._validate_answer(
        roof,
        "Плоская",
        {"1": "Современный минимализм"},
        False,
    )

    extras = _question("eskez-doma", "13")
    with pytest.raises(AppError) as exc:
        service._validate_answer(
            extras,
            ["Балкон"],
            {"4": "2 этажа", "12б": ["Второй этаж"]},
            False,
        )
    assert "inactive" in exc.value.detail
    service._validate_answer(
        extras,
        ["Балкон"],
        {"4": "2 этажа", "12б": ["Первый этаж"]},
        False,
    )


def test_house_floor_dependent_options_follow_selected_storeys() -> None:
    service = QuestionnaireService(None)
    terrace_floors = _question("eskez-doma", "12б")

    service._validate_answer(
        terrace_floors,
        ["Первый этаж"],
        {"4": "1 этаж", "12": "Терраса"},
        False,
    )
    with pytest.raises(AppError) as exc:
        service._validate_answer(
            terrace_floors,
            ["Второй этаж"],
            {"4": "1 этаж", "12": "Терраса"},
            False,
        )
    assert "inactive" in exc.value.detail

    service._validate_answer(
        terrace_floors,
        ["Первый этаж", "Второй этаж"],
        {"4": "2 этажа", "12": "Терраса"},
        False,
    )
    with pytest.raises(AppError):
        service._validate_answer(
            terrace_floors,
            ["Третий этаж"],
            {"4": "2 этажа", "12": "Терраса"},
            False,
        )
    service._validate_answer(
        terrace_floors,
        ["Мансарда"],
        {"4": "2 этажа + мансарда", "12": "Терраса"},
        False,
    )


def test_questionnaire_cannot_start_before_source_or_open_application_early() -> None:
    service = QuestionnaireService(None)
    catalog = build_catalog()

    before_source = DesignSession(
        catalog_version=CATALOG_VERSION,
        selected_objects=["eskez-doma"],
        current_object="eskez-doma",
        current_question_id="1",
    )
    with pytest.raises(AppError) as exc:
        service._validate(before_source, catalog, allow_submitted=False)
    assert "site photo" in exc.value.detail

    early_application = DesignSession(
        catalog_version=CATALOG_VERSION,
        selected_objects=["eskez-doma"],
        source_step_completed=True,
        current_object="zayavka",
        current_question_id="20",
    )
    with pytest.raises(AppError) as exc:
        service._validate(early_application, catalog, allow_submitted=False)
    assert "accepted sketch" in exc.value.detail

    wrong_initial_scene = DesignSession(
        catalog_version=CATALOG_VERSION,
        selected_objects=["eskez-doma"],
        source_step_completed=True,
        source_asset_id=None,
        scene_asset_id=uuid4(),
    )
    with pytest.raises(AppError) as exc:
        service._validate(wrong_initial_scene, catalog, allow_submitted=False)
    assert "one-time site source" in exc.value.detail


def test_acceptance_requires_all_visible_questions_and_positive_review() -> None:
    service = QuestionnaireService(None)
    catalog = build_catalog()
    session_id = uuid4()
    previous = DesignSession(
        session_id=session_id,
        catalog_version=CATALOG_VERSION,
        selected_objects=["lavochka"],
        current_object="lavochka",
        source_step_completed=True,
    )
    incomplete = previous.model_copy(
        update={
            "accepted_objects": ["lavochka"],
            "answers": {"lavochka": {"1": "Современная"}},
        },
        deep=True,
    )
    with pytest.raises(AppError) as exc:
        service._validate_acceptance_completion(previous, incomplete, catalog)
    assert "must be answered" in exc.value.detail

    definition = _definition("lavochka")
    answers = {}
    for question in definition["questions"]:
        if question["phase"] == "pre_render":
            answers[question["id"]] = question["options"][0]
    review = next(question for question in definition["questions"] if question["phase"] == "review")
    answers[review["id"]] = review["options"][1]
    negative = incomplete.model_copy(update={"answers": {"lavochka": answers}}, deep=True)
    with pytest.raises(AppError) as exc:
        service._validate_acceptance_completion(previous, negative, catalog)
    assert "positive sketch review" in exc.value.detail

    answers[review["id"]] = review["options"][0]
    accepted = negative.model_copy(update={"answers": {"lavochka": answers}}, deep=True)
    service._validate_acceptance_completion(previous, accepted, catalog)


def test_newly_accepted_object_requires_visual_lock_and_preserves_existing_locks() -> None:
    session_id = uuid4()
    house_generation = uuid4()
    bath_generation = uuid4()
    house_scene = uuid4()
    previous = DesignSession(
        session_id=session_id,
        catalog_version=CATALOG_VERSION,
        selected_objects=["eskez-doma", "banya"],
        source_step_completed=True,
        scene_asset_id=house_scene,
        accepted_objects=["eskez-doma"],
        generation_ids={"eskez-doma": house_generation},
        lock_regions={
            "eskez-doma": {"x": 0.2, "y": 0.15, "width": 0.6, "height": 0.65},
        },
    )
    accepted_without_lock = previous.model_copy(
        update={
            "accepted_objects": ["eskez-doma", "banya"],
            "generation_ids": {
                "eskez-doma": house_generation,
                "banya": bath_generation,
            },
        },
        deep=True,
    )
    with pytest.raises(AppError) as exc:
        QuestionnaireService._validate_accepted_object_locks(previous, accepted_without_lock)
    assert "visual lock region" in exc.value.detail

    accepted = accepted_without_lock.model_copy(deep=True)
    accepted.lock_regions["banya"] = {
        "x": 0.65,
        "y": 0.2,
        "width": 0.3,
        "height": 0.5,
    }
    accepted.edit_regions["banya"] = accepted.lock_regions["banya"]
    QuestionnaireService._validate_accepted_object_locks(previous, accepted)

    changed_house_lock = previous.model_copy(deep=True)
    changed_house_lock.lock_regions["eskez-doma"] = {
        "x": 0.1,
        "y": 0.1,
        "width": 0.7,
        "height": 0.7,
    }
    with pytest.raises(AppError) as exc:
        QuestionnaireService._validate_accepted_object_locks(previous, changed_house_lock)
    assert "cannot change its lock region" in exc.value.detail


def test_custom_option_requires_a_real_value_and_validates_numeric_bounds() -> None:
    service = QuestionnaireService(None)

    bath_area = _question("banya", "2")
    with pytest.raises(AppError) as exc:
        service._validate_answer(bath_area, "Свой вариант", {}, False)
    assert "custom questionnaire value" in exc.value.detail

    with pytest.raises(AppError) as exc:
        service._validate_answer(bath_area, "Свой вариант: 8", {}, False)
    assert "below" in exc.value.detail

    service._validate_answer(bath_area, "Свой вариант: 65", {}, False)

    gazebo_size = _question("besedka", "4")
    service._validate_answer(gazebo_size, "Свой вариант: 4×6 м", {}, False)
    with pytest.raises(AppError) as exc:
        service._validate_answer(gazebo_size, "Свой вариант:", {}, False)
    assert "must not be blank" in exc.value.detail


def test_catalog_bump_keeps_accepted_answers_but_revalidates_unfinished_answers() -> None:
    service = QuestionnaireService(None)
    catalog = build_catalog()
    session_id = uuid4()
    legacy_answers = {
        "banya": {
            "1": "Барнхаус",
            "9": "отделка дома",
        }
    }
    previous = DesignSession(
        session_id=session_id,
        catalog_version="2026-09-09.1",
        selected_objects=["banya"],
        source_step_completed=True,
        answers=legacy_answers,
        accepted_objects=["banya"],
    )
    upgraded = previous.model_copy(update={"catalog_version": CATALOG_VERSION}, deep=True)
    service._validate(upgraded, catalog, allow_submitted=False, previous=previous)

    unfinished_previous = previous.model_copy(
        update={"accepted_objects": []},
        deep=True,
    )
    unfinished = unfinished_previous.model_copy(
        update={"catalog_version": CATALOG_VERSION},
        deep=True,
    )
    with pytest.raises(AppError) as exc:
        service._validate(unfinished, catalog, allow_submitted=False, previous=unfinished_previous)
    assert "cannot be skipped" in exc.value.detail
