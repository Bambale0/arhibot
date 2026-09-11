from __future__ import annotations

import gzip
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOG_VERSION = "2026-09-11.1"

SECTION_SPECS = [
    ("house", "Дом", ["eskez-doma"]),
    ("buildings", "Дополнительные строения", ["gostevoy", "banya", "garazh", "naves", "letnyaya-kuhnya", "besedka", "hozblok", "teplica", "detskiy-domik"]),
    ("recreation", "Зоны отдыха", ["mangal", "basseyn", "kupel", "obedenaya"]),
    ("fences", "Ограждения", ["zabor", "izgorod", "vorota"]),
    ("site", "Мебель и площадки", ["lavochka", "kacheli", "igrovaya", "batut"]),
    ("landscape", "Ландшафтный дизайн", ["dorozhki", "gazon", "prud", "podsvetka", "podpornye"]),
]

OBJECT_TITLES = {
    "eskez-doma": "Дом, фасад",
    "gostevoy": "Гостевой дом",
    "banya": "Баня",
    "garazh": "Гараж, отдельный",
    "naves": "Навес для машин",
    "letnyaya-kuhnya": "Летняя кухня",
    "besedka": "Беседка",
    "hozblok": "Хозблок",
    "teplica": "Теплица",
    "detskiy-domik": "Детский домик",
    "mangal": "Мангальная зона",
    "basseyn": "Бассейн",
    "kupel": "Купель",
    "obedenaya": "Обеденная группа",
    "zabor": "Забор",
    "izgorod": "Живая изгородь",
    "vorota": "Ворота и калитка",
    "lavochka": "Лавочка",
    "kacheli": "Качели",
    "igrovaya": "Детская игровая",
    "batut": "Батут",
    "dorozhki": "Дорожки",
    "gazon": "Газон и посадки",
    "prud": "Пруд или ручей",
    "podsvetka": "Подсветка сада",
    "podpornye": "Подпорные стены",
    "zayavka": "Заявка",
}

# Questions whose roof is inherited from the accepted house when style == "Как у дома".
INHERITED_ROOF_QUESTION = {
    "gostevoy": "7", "banya": "8", "garazh": "5", "besedka": "6",
    "hozblok": "4", "detskiy-domik": "6", "letnyaya-kuhnya": "6",
}
STYLE_QUESTIONNAIRES = set(INHERITED_ROOF_QUESTION) | {"naves"}

FLAT_ROOF_STYLES = {"Современный минимализм", "Хай-тек", "Средиземноморский"}

_HOUSE_REQUIRED = {"1", "2", "3", "4", "5", "6", "7", "8"}
_HOUSE_MULTI = {"8": 3, "11": 2, "12б": 4, "13": 2, "13а2": 3}
_HOUSE_SKIP = {
    "9": "Стандартные окна",
    "10": "Газобетон",
    "11": [],
    "11б": "Нет",
    "12": "Нет",
    "12б": ["Первый этаж"],
    "13": [],
    "13а": "Открытый",
    "13а2": ["Второй этаж"],
    "13б": "На части кровли",
    "13б2": "Открытая",
    "14": "Дневной свет",
}

def _load_sources() -> dict[str, dict[str, str]]:
    path = Path(__file__).with_name("sources.json.gz")
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)

def _question_headers(text: str) -> list[tuple[int, str, str]]:
    """Find questionnaire question headers, excluding numbered answer options."""
    lines = text.splitlines()
    headers: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        match = re.match(r"^(\d+[а-яА-Яa-zA-Z]\d*)\.\s+(.+)$", stripped)
        if match:
            headers.append((index, match.group(1), match.group(2).strip()))
            continue
        match = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if not match:
            continue
        # Primary numbered questions are enclosed by dashed separators. Answer options
        # can also follow a dashed question separator, so require a dashed line on both sides.
        prev = index - 1
        while prev >= 0 and not lines[prev].strip():
            prev -= 1
        nxt = index + 1
        while nxt < len(lines) and not lines[nxt].strip():
            nxt += 1
        if (
            prev >= 0
            and nxt < len(lines)
            and lines[prev].strip().startswith("-" * 20)
            and lines[nxt].strip().startswith("-" * 20)
        ):
            headers.append((index, match.group(1), match.group(2).strip()))
    return headers

def _question_block(lines: list[str], headers: list[tuple[int, str, str]], pos: int) -> list[str]:
    start = headers[pos][0] + 1
    # Skip closing dashed line below primary question header.
    while start < len(lines) and (not lines[start].strip() or lines[start].strip().startswith("-" * 20)):
        start += 1
    end = headers[pos + 1][0] if pos + 1 < len(headers) else len(lines)
    # Stop before next section divider / PROPUSK summary.
    for idx in range(start, end):
        if lines[idx].strip().startswith("=" * 20):
            end = idx
            break
    return lines[start:end]

def user_question_title(title: str) -> str:
    """Hide customer logic annotations from user-facing questionnaire copy."""
    return re.sub(r"\s*\(\s*если\b[^)]*\)\s*$", "", title, flags=re.IGNORECASE).strip()


def _parse_question(
    qid: str, title: str, block: list[str], *, user_facing: bool = True
) -> dict[str, Any]:
    options: list[str] = []
    for line in block:
        match = re.match(r"^\s*\d+\.\s+(.+?\S)\s*$", line)
        if match:
            options.append(match.group(1))
    skip_default: str | list[str] | None = None
    for line in block:
        match = re.search(r"Пропуск\s*→\s*(.+?)\.?\s*$", line.strip())
        if match:
            skip_default = match.group(1).strip().rstrip(".")
            break
    notes = []
    for line in block:
        stripped = line.strip()
        if not stripped or re.match(r"^\d+\.\s+", stripped):
            continue
        if stripped.startswith(("Обязательн", "Пропуск →", "Можно несколько", "Поле:")):
            continue
        notes.append(stripped)

    field = next((line.strip().split(":", 1)[1].strip() for line in block if line.strip().startswith("Поле:")), None)
    kind = "single"
    if field and not options:
        kind = "text"
    if any("Можно несколько" in line for line in block) or "Можно несколько" in title:
        kind = "multi"
    return {
        "id": qid,
        "text": user_question_title(title) if user_facing else title.strip(),
        "kind": kind,
        "options": options,
        "required": any("Обязательн" in line for line in block),
        "skip_default": skip_default,
        "help": " ".join(notes) if notes else None,
        "field_hint": field,
        "max_selections": None,
        "phase": "pre_render",
        "condition": None,
        "option_rules": {},
        "edit_targets": {},
    }

def _parse_questions(
    key: str, text: str, *, user_facing: bool = True
) -> list[dict[str, Any]]:
    lines = text.splitlines()
    headers = _question_headers(text)
    questions = [
        _parse_question(
            qid, title, _question_block(lines, headers, pos), user_facing=user_facing
        )
        for pos, (_, qid, title) in enumerate(headers)
    ]
    # The house area is defined by hints instead of numbered choices.
    if key == "eskez-doma":
        by_id = {q["id"]: q for q in questions}
        by_id["3"]["kind"] = "number"
        by_id["3"]["options"] = ["100", "150", "200", "300", "Свой вариант"]
        by_id["3"]["field_hint"] = "свой вариант, от 40 до 1500 м²"
        by_id["3"]["min_value"] = 40
        by_id["3"]["max_value"] = 1500
        for qid in _HOUSE_REQUIRED:
            by_id[qid]["required"] = True
        for qid, max_count in _HOUSE_MULTI.items():
            by_id[qid]["kind"] = "multi"
            by_id[qid]["max_selections"] = max_count
        for qid, value in _HOUSE_SKIP.items():
            by_id[qid]["skip_default"] = value
        by_id["6а"]["condition"] = {"question_id": "6", "operator": "eq", "value": "Да"}
        by_id["6б"]["condition"] = {"question_id": "6а", "operator": "eq", "value": "Не в доме"}
        by_id["6в"]["condition"] = {
            "operator": "any",
            "conditions": [
                {"question_id": "6а", "operator": "eq", "value": "В доме"},
                {"question_id": "6б", "operator": "in", "value": ["Навес", "Пристроен к дому"]},
            ],
        }
        by_id["12б"]["condition"] = {
            "operator": "all",
            "conditions": [
                {"question_id": "12", "operator": "neq", "value": "Нет"},
                {"question_id": "4", "operator": "neq", "value": "1 этаж"},
            ],
        }
        by_id["13а"]["condition"] = {"question_id": "13", "operator": "contains", "value": "Балкон"}
        by_id["13а2"]["condition"] = {"question_id": "13", "operator": "contains", "value": "Балкон"}
        by_id["13б"]["condition"] = {"question_id": "13", "operator": "contains", "value": "Терраса на плоской кровле"}
        by_id["13б2"]["condition"] = {"question_id": "13", "operator": "contains", "value": "Терраса на плоской кровле"}
        by_id["7"]["option_rules"]["Плоская"] = {"question_id": "1", "operator": "in", "value": sorted(FLAT_ROOF_STYLES)}
        if "13" in by_id:
            by_id["13"]["option_rules"]["Терраса на плоской кровле"] = {"question_id": "7", "operator": "eq", "value": "Плоская"}
            by_id["13"]["option_rules"]["Балкон"] = {
                "operator": "all",
                "conditions": [
                    {"question_id": "4", "operator": "neq", "value": "1 этаж"},
                    {
                        "question_id": "12б",
                        "operator": "not_contains_any",
                        "value": ["Второй этаж", "Третий этаж", "Мансарда"],
                    },
                ],
            }
        by_id["15"]["phase"] = "review"
        by_id["15"]["required"] = True
        by_id["15а"]["phase"] = "review"
        by_id["15а"]["required"] = True
        by_id["15а"]["condition"] = {"question_id": "15", "operator": "starts_with", "value": "Нет"}
        by_id["15б"]["phase"] = "review"
        by_id["15б"]["kind"] = "multi"
        by_id["15б"]["required"] = True
        by_id["15б"]["condition"] = {"question_id": "15а", "operator": "starts_with", "value": "Что-то конкретное"}
        by_id["15б"]["options"] = [
            "Стиль", "Форма дома", "Размер и этажность", "Цоколь",
            "Гараж, навес, пристрой", "Кровля", "Материалы фасада", "Окна",
            "Терраса, балкон, кровля", "Второй свет или зимний сад",
            "Камин, труба", "Освещение",
        ]
        by_id["15б"]["edit_targets"] = {
            "Стиль": ["1"],
            "Форма дома": ["2"],
            "Размер и этажность": ["3", "4"],
            "Цоколь": ["5"],
            "Гараж, навес, пристрой": ["6", "6а", "6б", "6в"],
            "Кровля": ["7"],
            "Материалы фасада": ["8"],
            "Окна": ["9"],
            "Терраса, балкон, кровля": ["12", "12б", "13", "13а", "13а2", "13б", "13б2"],
            "Второй свет или зимний сад": ["11"],
            "Камин, труба": ["11б"],
            "Освещение": ["14"],
        }
        by_id["15б"]["field_hint"] = "Свой комментарий"
    else:
        if questions:
            questions[-1]["phase"] = "review"
            questions[-1]["required"] = True

    return questions

def _apply_common_overrides(key: str, questions: list[dict[str, Any]]) -> None:
    by_id = {q["id"]: q for q in questions}
    roof_id = INHERITED_ROOF_QUESTION.get(key)
    if roof_id and roof_id in by_id:
        by_id[roof_id]["condition"] = {"question_id": "1", "operator": "neq", "value": "Как у дома"}
        by_id[roof_id]["option_rules"]["Плоская"] = {"question_id": "1", "operator": "in", "value": sorted(FLAT_ROOF_STYLES)}
        by_id[roof_id]["required"] = True

    if key in STYLE_QUESTIONNAIRES and "1" in by_id:
        by_id["1"]["option_rules"]["Как у дома"] = {"operator": "house_accepted"}

    # These source files allow skipping facade material only when style is inherited.
    conditional_facade_skip = {
        "gostevoy": "8",
        "banya": "9",
        "garazh": "6",
        "letnyaya-kuhnya": "7",
        "hozblok": "5",
    }
    facade_skip_id = conditional_facade_skip.get(key)
    if facade_skip_id and facade_skip_id in by_id:
        by_id[facade_skip_id]["skip_default"] = "отделка дома"
        by_id[facade_skip_id]["skip_condition"] = {
            "question_id": "1",
            "operator": "eq",
            "value": "Как у дома",
        }

    # Explicit selection limits stated by the source.
    limits = {
        ("gostevoy", "8"): 3, ("banya", "9"): 3, ("garazh", "6"): 3,
        ("hozblok", "5"): 3, ("letnyaya-kuhnya", "7"): 3,
        ("zabor", "4"): 2,
    }
    for (object_key, qid), max_count in limits.items():
        if key == object_key and qid in by_id:
            by_id[qid]["kind"] = "multi"
            by_id[qid]["max_selections"] = max_count

    # Known source questions that are multi-select even when the prose does not repeat the marker.
    for object_key, qid in {
        ("gazon", "2"), ("podsvetka", "1"), ("dorozhki", "2"),
        ("banya", "11"), ("hozblok", "6"),
    }:
        if key == object_key and qid in by_id:
            by_id[qid]["kind"] = "multi"

    # Numeric custom fields defined in source prose.
    numeric = {
        ("banya", "2"): (12, 150, None),
        ("gostevoy", "3"): (20, 200, ["40", "60", "80", "Свой вариант"]),
        ("letnyaya-kuhnya", "3"): (8, 80, ["15", "25", "40", "Свой вариант"]),
    }
    for (object_key, qid), (min_value, max_value, hints) in numeric.items():
        if key == object_key and qid in by_id:
            by_id[qid]["min_value"] = min_value
            by_id[qid]["max_value"] = max_value
            if hints:
                by_id[qid]["kind"] = "number"
                by_id[qid]["options"] = hints

    required_ids = {
        "gostevoy": {"1", "2", "3", "4", "5", "6", "11"},
        "banya": {"1", "2", "3", "4", "5", "6", "7", "12"},
        "garazh": {"1", "2", "4", "8"},
        "naves": {"1", "2", "3", "4", "8"},
        "letnyaya-kuhnya": {"1", "2", "3", "4", "5", "9"},
        "besedka": {"1", "2", "3", "4", "5", "8"},
        "hozblok": {"1", "2", "3", "7"},
        "teplica": {"1", "2", "3", "4", "6"},
        "detskiy-domik": {"1", "2", "3", "5", "7"},
        "mangal": {"1", "3", "5"},
        "basseyn": {"1", "2", "3", "5", "6", "8"},
        "kupel": {"1", "3", "4"},
        "obedenaya": {"1", "3", "5"},
        "zabor": {"1", "2", "7"},
        "izgorod": {"1", "2", "3", "4"},
        "vorota": {"1", "5"},
        "lavochka": {"1", "2", "3"},
        "kacheli": {"1", "3", "4"},
        "igrovaya": {"1", "3", "4"},
        "batut": {"1", "3", "4"},
        "dorozhki": {"1", "2", "3"},
        "gazon": {"1", "3"},
        "prud": {"1", "2", "3", "4"},
        "podsvetka": {"1", "3"},
        "podpornye": {"1", "2", "3", "4"},
    }
    for qid in required_ids.get(key, set()):
        if qid in by_id:
            by_id[qid]["required"] = True

    # House-dependent branch answers are mandatory when their condition is active.
    if key == "eskez-doma":
        for qid in ("6а", "6б", "6в"):
            if qid in by_id:
                by_id[qid]["required"] = True

    # Prevent the impossible source combination "only wicket" + "no wicket".
    if key == "vorota" and "2" in by_id:
        by_id["2"]["condition"] = {"question_id": "1", "operator": "neq", "value": "Без ворот, только калитка"}

def _application_questions(text: str, *, user_facing: bool = True) -> list[dict[str, Any]]:
    questions = _parse_questions("zayavka", text, user_facing=user_facing)
    by_id = {q["id"]: q for q in questions}
    for qid in ("20", "21", "22", "23", "24", "25"):
        by_id[qid]["required"] = True
        by_id[qid]["phase"] = "application"
    by_id["23"]["kind"] = "text"
    by_id["24"]["kind"] = "text"
    if user_facing:
        by_id["24"]["text"] = "Оставьте телефон или @username Telegram"
        by_id["24"]["field_hint"] = "Телефон или @username Telegram"
    by_id["25"]["kind"] = "consent"
    by_id["25"]["options"] = []
    return questions

@lru_cache(maxsize=4)
def build_catalog(
    *, user_facing: bool = True, version: str = CATALOG_VERSION
) -> dict[str, Any]:
    sources = _load_sources()
    definitions: list[dict[str, Any]] = []
    for _, _, keys in SECTION_SPECS:
        for order, key in enumerate(keys):
            source = sources[key]
            questions = _parse_questions(key, source["text"], user_facing=user_facing)
            _apply_common_overrides(key, questions)
            definitions.append({
                "key": key,
                "title": OBJECT_TITLES[key],
                "source_file": source["filename"],
                "order": order,
                "questions": questions,
                "scene_policy": {
                    "camera": "Дом: дрон 40–50 м, сверху угловой. Остальные объекты: как у принятого кадра дома; без дома — дрон сверху угловой.",
                    "lighting": "У дома — ответ шага 14. Остальные объекты наследуют свет текущего кадра.",
                    "placement": "Каждый следующий объект добавляется в текущий принятый кадр, если он есть.",
                },
            })
    app_source = sources["zayavka"]
    definitions.append({
        "key": "zayavka",
        "title": OBJECT_TITLES["zayavka"],
        "source_file": app_source["filename"],
        "order": 999,
        "questions": _application_questions(app_source["text"], user_facing=user_facing),
        "scene_policy": None,
    })
    sections = [
        {
            "key": section_key,
            "title": title,
            "object_keys": object_keys,
        }
        for section_key, title, object_keys in SECTION_SPECS
    ]
    return {
        "version": version,
        "sections": sections,
        "questionnaires": definitions,
        "application_key": "zayavka",
        "source_rules": [
            "Фото участка или «Продолжить без фото» — один раз, до опросника.",
            "Если есть принятый эскиз дома — следующие объекты сажаем на этот кадр.",
            "У основного дома и гостевого планировок нет. Комнаты не спрашиваем.",
            "Кнопка «Пропустить» доступна только там, где исходный файл явно разрешает пропуск; применяется указанное значение по умолчанию.",
            "После принятия объекта пользователь сам выбирает следующий объект или переходит к заявке.",
            "Принятые объекты и их ответы фиксируются и не редактируются в текущей сессии.",
            "Заявка открывается только после принятого эскиза и после отправки доставляется администратору в Telegram.",
        ],
    }
