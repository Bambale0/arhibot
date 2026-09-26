from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from enum import StrEnum


class EditIntent(StrEnum):
    FACADE_FINISH = "facade_finish"
    FACADE_GEOMETRY = "facade_geometry"
    ROOF_FINISH = "roof_finish"
    ROOF_GEOMETRY = "roof_geometry"
    WINDOWS_FINISH = "windows_finish"
    WINDOWS_GEOMETRY = "windows_geometry"
    DOOR = "door"
    TERRACE = "terrace"
    BALCONY = "balcony"
    EXTENSION = "extension"
    EXTERIOR_LIGHTING = "exterior_lighting"
    LANDSCAPE = "landscape"
    CHIMNEY_FINISH = "chimney_finish"
    CHIMNEY_GEOMETRY = "chimney_geometry"
    WHOLE_HOUSE_GEOMETRY = "whole_house_geometry"
    INTERIOR = "interior"
    MIXED_INTERIOR_EXTERIOR = "mixed_interior_exterior"
    GENERIC_EXTERIOR = "generic_exterior"
    OBJECT_REMOVAL = "object_removal"


class EditDomain(StrEnum):
    EXTERIOR = "exterior"
    INTERIOR = "interior"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class EditPolicySnapshot:
    version: str
    domain: EditDomain
    intent: EditIntent
    allow_generation: bool
    composition_mode: str
    sanitized_comment: str
    interior_request_detected: bool
    preserve_camera: bool
    preserve_building_geometry: bool
    preserve_visible_interior: bool
    allow_interior_reconstruction: bool
    allow_fireplace_relocation: bool
    allow_chimney_relocation: bool
    scene_analysis_required: bool
    structural_links: tuple[str, ...]
    quality_checks: tuple[str, ...]
    enforced_quality_checks: tuple[str, ...]
    deferred_quality_checks: tuple[str, ...]
    scene_analysis_enforced: bool

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["domain"] = self.domain.value
        data["intent"] = self.intent.value
        data["structural_links"] = list(self.structural_links)
        data["quality_checks"] = list(self.quality_checks)
        data["enforced_quality_checks"] = list(self.enforced_quality_checks)
        data["deferred_quality_checks"] = list(self.deferred_quality_checks)
        return data


_INTERIOR_MARKERS = (
    "интерьер",
    "диван",
    "кровать",
    "мебел",
    "комнат",
    "спальн",
    "сануз",
    "ванн",
    "лестниц",
    "перегород",
    "планиров",
    "внутренн",
    "внутри дома",
    "кухня внутри",
    "кухню внутри",
    "кухне внутри",
    "стол внутри",
    "стена внутри",
    "стены внутри",
    "стену внутри",
)
_FIREPLACE_EDIT_ACTIONS = (
    "перенес",
    "перенос",
    "передвин",
    "передвиг",
    "перемест",
    "перемещ",
    "смест",
    "смещ",
    "добав",
    "убер",
    "убрат",
    "убир",
    "замен",
    "измен",
    "меня",
    "сдела",
)
_FIREPLACE_CHIMNEY_PATTERNS = (
    re.compile(r"\bкаминн\w*\s+(?:труб\w*|дымоход\w*)\b", re.IGNORECASE),
    re.compile(r"\b(?:труб\w*|дымоход\w*)\s+(?:от\s+)?камин\w*\b", re.IGNORECASE),
)
_COMMENT_CLAUSE_SPLIT_RE = re.compile(
    r"(?<=[.!?;])\s+|,\s*|\s+(?:а\s+ещ[её]|и)\s+",
    re.IGNORECASE,
)
_GEOMETRY_MARKERS = (
    "перенес",
    "передвин",
    "перемест",
    "смест",
    "размер",
    "увелич",
    "уменьш",
    "положен",
    "располож",
    "геометр",
    "форм",
    "количеств",
)
_ROOF_GEOMETRY_MARKERS = (
    "двускат",
    "односкат",
    "четырехскат",
    "четырёхскат",
    "вальмов",
    "плоск",
    "мансард",
    "уклон",
    "поднять крыш",
    "опустить крыш",
    *_GEOMETRY_MARKERS,
)
_CHIMNEY_GEOMETRY_MARKERS = (
    "другой скат",
    "другую сторону",
    "другом скате",
    "перенес",
    "передвин",
    "перемест",
    "смест",
)
_HOUSE_STRUCTURAL_INTENTS = {
    EditIntent.ROOF_FINISH,
    EditIntent.ROOF_GEOMETRY,
    EditIntent.WINDOWS_GEOMETRY,
    EditIntent.CHIMNEY_FINISH,
    EditIntent.CHIMNEY_GEOMETRY,
    EditIntent.WHOLE_HOUSE_GEOMETRY,
    EditIntent.FACADE_GEOMETRY,
    EditIntent.TERRACE,
    EditIntent.BALCONY,
    EditIntent.EXTENSION,
}
_HOUSE_ID_INTENTS: dict[str, EditIntent] = {
    "1": EditIntent.GENERIC_EXTERIOR,
    "2": EditIntent.WHOLE_HOUSE_GEOMETRY,
    "3": EditIntent.WHOLE_HOUSE_GEOMETRY,
    "4": EditIntent.WHOLE_HOUSE_GEOMETRY,
    "5": EditIntent.FACADE_FINISH,
    "6": EditIntent.EXTENSION,
    "6а": EditIntent.EXTENSION,
    "6б": EditIntent.EXTENSION,
    "6в": EditIntent.EXTENSION,
    "7": EditIntent.ROOF_FINISH,
    "8": EditIntent.FACADE_FINISH,
    "9": EditIntent.WINDOWS_FINISH,
    "11": EditIntent.FACADE_GEOMETRY,
    "11б": EditIntent.CHIMNEY_FINISH,
    "12": EditIntent.TERRACE,
    "12б": EditIntent.TERRACE,
    "13": EditIntent.BALCONY,
    "13а": EditIntent.BALCONY,
    "13а2": EditIntent.BALCONY,
    "13б": EditIntent.BALCONY,
    "13б2": EditIntent.BALCONY,
    "14": EditIntent.EXTERIOR_LIGHTING,
}


def _contains(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in markers)


def _strip_chimney_fireplace_phrases(text: str) -> str:
    cleaned = text
    for pattern in _FIREPLACE_CHIMNEY_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return cleaned


def _action_is_negated(text: str, action_start: int) -> bool:
    prefix = text[max(0, action_start - 24) : action_start]
    return re.search(r"(?:^|\s)не(?:\s+(?:надо|нужно))?\s*$", prefix) is not None


def _has_non_negated_action(text: str, markers: tuple[str, ...]) -> bool:
    for marker in markers:
        start = 0
        while True:
            index = text.find(marker, start)
            if index < 0:
                break
            if index > 0 and text[index - 1].isalnum():
                start = index + len(marker)
                continue
            if not _action_is_negated(text, index):
                return True
            start = index + len(marker)
    return False


def _fireplace_edit_requested(text: str) -> bool:
    for clause in _COMMENT_CLAUSE_SPLIT_RE.split(text.casefold()):
        normalized = _strip_chimney_fireplace_phrases(clause)
        if "камин" not in normalized:
            continue
        if _has_non_negated_action(normalized, _FIREPLACE_EDIT_ACTIONS):
            return True
    return False


def _interior_clause(text: str) -> bool:
    return _contains(text, _INTERIOR_MARKERS) or _fireplace_edit_requested(text)


def _sanitize_comment(comment: str) -> tuple[str, bool]:
    stripped = comment.strip()
    if not stripped:
        return "", False
    if not _interior_clause(stripped):
        return stripped, False

    parts = [
        part.strip(" .!?;,-")
        for part in _COMMENT_CLAUSE_SPLIT_RE.split(stripped)
    ]
    kept = [part for part in parts if part and not _interior_clause(part)]
    return ". ".join(kept), True


def _resolve_house_intent(edit_question_ids: list[str], comment: str) -> EditIntent:
    ids = set(edit_question_ids)
    lowered = comment.casefold()

    if "11б" in ids:
        if _contains(lowered, _CHIMNEY_GEOMETRY_MARKERS):
            return EditIntent.CHIMNEY_GEOMETRY
        return EditIntent.CHIMNEY_FINISH

    if "7" in ids:
        if _contains(lowered, _ROOF_GEOMETRY_MARKERS):
            return EditIntent.ROOF_GEOMETRY
        return EditIntent.ROOF_FINISH

    if "9" in ids:
        if _contains(lowered, _GEOMETRY_MARKERS):
            return EditIntent.WINDOWS_GEOMETRY
        return EditIntent.WINDOWS_FINISH

    intents = {_HOUSE_ID_INTENTS.get(question_id) for question_id in ids}
    intents.discard(None)
    if not intents:
        return EditIntent.GENERIC_EXTERIOR
    if len(intents) == 1:
        return next(iter(intents))
    if EditIntent.WHOLE_HOUSE_GEOMETRY in intents:
        return EditIntent.WHOLE_HOUSE_GEOMETRY
    if intents & _HOUSE_STRUCTURAL_INTENTS:
        return EditIntent.FACADE_GEOMETRY
    return EditIntent.GENERIC_EXTERIOR


def build_edit_policy(
    *,
    object_key: str,
    edit_question_ids: list[str],
    review_comment: str,
) -> EditPolicySnapshot:
    sanitized_comment, interior_detected = _sanitize_comment(review_comment)
    fireplace_relocation = _fireplace_edit_requested(review_comment)

    if fireplace_relocation:
        return EditPolicySnapshot(
            version="exterior-edit-policy.v1",
            domain=EditDomain.INTERIOR,
            intent=EditIntent.INTERIOR,
            allow_generation=False,
            composition_mode="masked_edit",
            sanitized_comment="",
            interior_request_detected=True,
            preserve_camera=True,
            preserve_building_geometry=True,
            preserve_visible_interior=True,
            allow_interior_reconstruction=False,
            allow_fireplace_relocation=False,
            allow_chimney_relocation=False,
            scene_analysis_required=False,
            structural_links=("fireplace_chimney",),
            quality_checks=("outside_region_integrity", "boundary_continuity"),
            enforced_quality_checks=(),
            deferred_quality_checks=(),
            scene_analysis_enforced=False,
        )

    if interior_detected and not edit_question_ids and not sanitized_comment:
        return EditPolicySnapshot(
            version="exterior-edit-policy.v1",
            domain=EditDomain.INTERIOR,
            intent=EditIntent.INTERIOR,
            allow_generation=False,
            composition_mode="masked_edit",
            sanitized_comment="",
            interior_request_detected=True,
            preserve_camera=True,
            preserve_building_geometry=True,
            preserve_visible_interior=True,
            allow_interior_reconstruction=False,
            allow_fireplace_relocation=False,
            allow_chimney_relocation=False,
            scene_analysis_required=False,
            structural_links=("fireplace_chimney",) if object_key == "eskez-doma" else (),
            quality_checks=("outside_region_integrity", "boundary_continuity"),
            enforced_quality_checks=(),
            deferred_quality_checks=(),
            scene_analysis_enforced=False,
        )

    intent = (
        _resolve_house_intent(edit_question_ids, sanitized_comment)
        if object_key == "eskez-doma"
        else EditIntent.GENERIC_EXTERIOR
    )
    domain = EditDomain.MIXED if interior_detected else EditDomain.EXTERIOR
    structural_sensitive = object_key == "eskez-doma" and intent in _HOUSE_STRUCTURAL_INTENTS
    geometry_intents = {
        EditIntent.FACADE_GEOMETRY,
        EditIntent.ROOF_GEOMETRY,
        EditIntent.WINDOWS_GEOMETRY,
        EditIntent.CHIMNEY_GEOMETRY,
        EditIntent.WHOLE_HOUSE_GEOMETRY,
        EditIntent.TERRACE,
        EditIntent.BALCONY,
        EditIntent.EXTENSION,
    }
    checks = [
        "outside_region_integrity",
        "boundary_continuity",
        "interior_preservation",
    ]
    if structural_sensitive:
        checks.append("structural_link_consistency")

    enforced_checks = ("outside_region_integrity", "boundary_continuity")
    deferred_checks = tuple(
        check for check in checks if check not in enforced_checks
    )

    return EditPolicySnapshot(
        version="exterior-edit-policy.v1",
        domain=domain,
        intent=intent,
        allow_generation=True,
        composition_mode="masked_edit",
        sanitized_comment=sanitized_comment,
        interior_request_detected=interior_detected,
        preserve_camera=True,
        preserve_building_geometry=intent not in geometry_intents,
        preserve_visible_interior=True,
        allow_interior_reconstruction=False,
        allow_fireplace_relocation=False,
        allow_chimney_relocation=intent == EditIntent.CHIMNEY_GEOMETRY,
        scene_analysis_required=structural_sensitive,
        structural_links=("fireplace_chimney",) if object_key == "eskez-doma" else (),
        quality_checks=tuple(checks),
        enforced_quality_checks=enforced_checks,
        deferred_quality_checks=deferred_checks,
        scene_analysis_enforced=False,
    )


def build_object_removal_policy(object_key: str) -> EditPolicySnapshot:
    base = build_edit_policy(object_key=object_key, edit_question_ids=[], review_comment="")
    return replace(
        base,
        intent=EditIntent.OBJECT_REMOVAL,
        preserve_building_geometry=False,
        preserve_visible_interior=False,
        structural_links=(),
        quality_checks=("outside_region_integrity", "boundary_continuity"),
        deferred_quality_checks=(),
    )
