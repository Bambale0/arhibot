from app.questionnaires.catalog import CATALOG_VERSION, _load_sources, build_catalog
from app.schemas.questionnaires import DesignSession, QuestionnaireCatalogResponse


def _definition(key: str) -> dict:
    return next(item for item in build_catalog()["questionnaires"] if item["key"] == key)


def _question(key: str, question_id: str) -> dict:
    return next(item for item in _definition(key)["questions"] if item["id"] == question_id)


def test_questionnaire_catalog_matches_source_bundle() -> None:
    catalog = QuestionnaireCatalogResponse.model_validate(build_catalog())
    sources = _load_sources()
    assert catalog.version == "2026-09-08"
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
