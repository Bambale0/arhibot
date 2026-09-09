from app.questionnaires.catalog import build_catalog


EXPECTED_DESIGN_OBJECTS = [
    "eskez-doma",
    "gostevoy",
    "banya",
    "garazh",
    "naves",
    "letnyaya-kuhnya",
    "besedka",
    "hozblok",
    "teplica",
    "detskiy-domik",
    "mangal",
    "basseyn",
    "kupel",
    "obedenaya",
    "zabor",
    "izgorod",
    "vorota",
    "lavochka",
    "kacheli",
    "igrovaya",
    "batut",
    "dorozhki",
    "gazon",
    "prud",
    "podsvetka",
    "podpornye",
]


def _definition(key: str) -> dict:
    return next(item for item in build_catalog()["questionnaires"] if item["key"] == key)


def _question_blob(key: str) -> str:
    definition = _definition(key)
    parts: list[str] = []
    for question in definition["questions"]:
        parts.append(question["text"])
        parts.extend(question.get("options", []))
    return " ".join(parts).lower()


def test_tz_has_section_then_multi_object_catalog_with_application_separate() -> None:
    catalog = build_catalog()
    ordered = [key for section in catalog["sections"] for key in section["object_keys"]]
    assert ordered == EXPECTED_DESIGN_OBJECTS
    assert len(ordered) == 26
    assert catalog["application_key"] == "zayavka"
    assert len(catalog["questionnaires"]) == 27
    assert "zayavka" not in ordered


def test_tz_house_and_guest_do_not_ask_for_layouts_or_rooms() -> None:
    forbidden = (
        "планиров",
        "спальн",
        "сануз",
        "кухня-гост",
        "комнат",
    )
    for key in ("eskez-doma", "gostevoy"):
        blob = _question_blob(key)
        assert not any(term in blob for term in forbidden), (key, blob)


def test_tz_has_no_separate_plot_start_question() -> None:
    for key in EXPECTED_DESIGN_OBJECTS:
        blob = _question_blob(key)
        assert "участок уже есть" not in blob
        assert "сколько сот" not in blob
    application = _definition("zayavka")
    assert application["questions"][0]["id"] == "20"
    assert application["questions"][0]["text"] == "Участок уже есть?"


def test_tz_garage_and_car_canopy_scopes_stay_separate() -> None:
    house_ids = {question["id"] for question in _definition("eskez-doma")["questions"]}
    assert {"6", "6а", "6б", "6в"}.issubset(house_ids)

    garage = _definition("garazh")
    assert garage["title"] == "Гараж, отдельный"
    garage_blob = _question_blob("garazh")
    assert "встроенный" not in garage_blob
    assert "пристроен к дому" not in garage_blob
    assert "навес" not in garage_blob

    canopy = _definition("naves")
    assert canopy["title"] == "Навес для машин"
    assert "машин" in _question_blob("naves")


def test_tz_pool_and_hot_tub_are_not_bath_or_house_room_questions() -> None:
    house_blob = _question_blob("eskez-doma")
    bath_blob = _question_blob("banya")
    assert "бассейн" not in house_blob
    assert "бассейн" not in bath_blob
    assert "купел" not in bath_blob
    assert _definition("basseyn")["source_file"] == "oprosnik-basseyn.txt"
    assert _definition("kupel")["source_file"] == "oprosnik-kupel.txt"


def test_tz_swing_cover_is_in_swings_not_car_canopy_questionnaire() -> None:
    swings = _definition("kacheli")
    cover = next(question for question in swings["questions"] if question["id"] == "2")
    assert cover["text"] == "Чем накрыть?"
    assert "Без навеса" in cover["options"]
    assert "качел" not in _question_blob("naves")


def test_tz_every_design_object_ends_in_accept_or_refine_review() -> None:
    for key in EXPECTED_DESIGN_OBJECTS:
        reviews = [
            question
            for question in _definition(key)["questions"]
            if question["phase"] == "review"
        ]
        assert reviews, key
        assert reviews[0]["options"][0].startswith("Да"), key
        assert reviews[0]["options"][1].startswith("Нет"), key


def test_tz_scene_policy_uses_last_accepted_frame() -> None:
    for key in EXPECTED_DESIGN_OBJECTS:
        policy = _definition(key)["scene_policy"]
        assert policy is not None
        assert "текущий принятый кадр" in policy["placement"].lower()


def test_tz_custom_option_questions_keep_a_real_value_path() -> None:
    expected = {
        ("eskez-doma", "3"),
        ("gostevoy", "3"),
        ("banya", "2"),
        ("letnyaya-kuhnya", "3"),
        ("besedka", "4"),
        ("hozblok", "2"),
        ("detskiy-domik", "2"),
        ("basseyn", "3"),
    }
    actual = {
        (definition["key"], question["id"])
        for definition in build_catalog()["questionnaires"]
        for question in definition["questions"]
        if "Свой вариант" in question.get("options", [])
    }
    assert actual == expected

    for key, question_id in (("eskez-doma", "3"), ("gostevoy", "3"), ("banya", "2"), ("letnyaya-kuhnya", "3")):
        question = next(item for item in _definition(key)["questions"] if item["id"] == question_id)
        assert question.get("min_value") is not None
        assert question.get("max_value") is not None
