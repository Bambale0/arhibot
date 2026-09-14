from __future__ import annotations

from math import sqrt
from typing import Any

from app.architecture.schemas import (
    AccentMaterialPreset,
    ArchitecturePackage,
    FacadeMaterialPreset,
    GlazingMaterialPreset,
    HouseAppearance,
    HouseGeometry,
    HouseProgram,
    LevelGeometry,
    PbrMaterialPalette,
    Point2D,
    Polygon2D,
    RoofGeometry,
    RoofMaterialPreset,
    RoofType,
)
from app.core.errors import AppError
from app.schemas.questionnaires import DesignSession

_HOUSE_KEY = "eskez-doma"
_LEVEL_HEIGHT_M = 3.2
_FOOTPRINT_ASPECT_RATIO = 1.25


def _house_answers(session: DesignSession) -> dict[str, Any]:
    if _HOUSE_KEY not in session.selected_objects:
        raise AppError(
            type="questionnaire_house_required",
            title="House questionnaire required",
            status=422,
            detail="Canonical house geometry can be compiled only for a project containing the house questionnaire.",
        )
    answers = session.answers.get(_HOUSE_KEY)
    if not answers:
        raise AppError(
            type="questionnaire_house_incomplete",
            title="House questionnaire incomplete",
            status=422,
            detail="Complete the house questionnaire before compiling canonical geometry.",
        )
    return answers


def _gross_area(answers: dict[str, Any]) -> float:
    raw = answers.get("3")
    try:
        area = float(raw)
    except (TypeError, ValueError) as exc:
        raise AppError(
            type="questionnaire_house_area_missing",
            title="House area missing",
            status=422,
            detail="The house questionnaire must contain a numeric gross floor area.",
        ) from exc
    if not 40 <= area <= 1500:
        raise AppError(
            type="questionnaire_house_area_invalid",
            title="House area invalid",
            status=422,
            detail="House gross floor area must be between 40 and 1500 m².",
        )
    return area


def _level_count(answers: dict[str, Any]) -> int:
    value = str(answers.get("4") or "").strip().lower()
    if value.startswith("1 "):
        return 1
    if value.startswith("2 ") and "мансард" in value:
        return 3
    if value.startswith("2 "):
        return 2
    if value.startswith("3 "):
        return 3
    raise AppError(
        type="questionnaire_house_storeys_missing",
        title="House storeys missing",
        status=422,
        detail="The house questionnaire must contain a supported storey configuration.",
    )


def _rect(width: float, depth: float) -> Polygon2D:
    return Polygon2D(
        points=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=width, y=0.0),
            Point2D(x=width, y=depth),
            Point2D(x=0.0, y=depth),
        ]
    )


def _levels(*, gross_area: float, level_count: int) -> tuple[list[LevelGeometry], float, float]:
    footprint_area = gross_area / level_count
    width = sqrt(footprint_area * _FOOTPRINT_ASPECT_RATIO)
    depth = footprint_area / width
    footprint = _rect(width, depth)
    levels = [
        LevelGeometry(
            id=f"level_{index + 1}",
            label=("GROUND FLOOR" if index == 0 else f"LEVEL {index + 1}"),
            z=index * _LEVEL_HEIGHT_M,
            height=_LEVEL_HEIGHT_M,
            footprint=footprint,
        )
        for index in range(level_count)
    ]
    return levels, width, depth


def _roof(answers: dict[str, Any], *, level_count: int, width: float, depth: float) -> RoofGeometry:
    top = level_count * _LEVEL_HEIGHT_M
    roof_answer = str(answers.get("7") or "").lower()
    if "плоск" in roof_answer:
        return RoofGeometry(type=RoofType.FLAT, eave_z=top, ridge_z=top)
    return RoofGeometry(
        type=RoofType.GABLE,
        eave_z=top,
        ridge_z=top + min(3.0, max(1.4, width * 0.18)),
        ridge_start=Point2D(x=width / 2, y=0.0),
        ridge_end=Point2D(x=width / 2, y=depth),
    )


def _facade_preset(answers: dict[str, Any]) -> FacadeMaterialPreset:
    raw = answers.get("8")
    values = raw if isinstance(raw, list) else [raw]
    text = " ".join(str(item or "") for item in values).lower()
    if "кирп" in text:
        return FacadeMaterialPreset.RED_BRICK
    if "кам" in text:
        return FacadeMaterialPreset.WARM_STONE
    if "дерев" in text or "планкен" in text or "брус" in text:
        return FacadeMaterialPreset.WOOD_CLADDING
    if "панел" in text or "металл" in text:
        return FacadeMaterialPreset.GRAPHITE_PANEL
    return FacadeMaterialPreset.WHITE_PLASTER


def _roof_preset(answers: dict[str, Any]) -> RoofMaterialPreset:
    text = str(answers.get("7") or "").lower()
    if "череп" in text:
        return RoofMaterialPreset.BROWN_TILE
    if "плоск" in text:
        return RoofMaterialPreset.GRAY_MEMBRANE
    return RoofMaterialPreset.DARK_METAL


def _glazing_preset(answers: dict[str, Any]) -> GlazingMaterialPreset:
    text = str(answers.get("9") or "").lower()
    if "тонир" in text or "темн" in text:
        return GlazingMaterialPreset.SMOKED_GLASS
    if "панорам" in text or "энерг" in text:
        return GlazingMaterialPreset.LOW_E_GLASS
    return GlazingMaterialPreset.CLEAR_GLASS


def compile_house_architecture(session: DesignSession) -> ArchitecturePackage:
    """Compile explicit questionnaire facts into a conservative canonical geometry seed.

    The compiler deliberately does not invent rooms, openings or decorative geometry that the
    questionnaire does not locate in metric coordinates. Later AI/agent refinement must preserve
    this package contract and pass GeometryValidator before replacing the seed.
    """

    answers = _house_answers(session)
    gross_area = _gross_area(answers)
    level_count = _level_count(answers)
    levels, width, depth = _levels(gross_area=gross_area, level_count=level_count)

    appearance = HouseAppearance(
        architecture_style=str(answers.get("1") or "") or None,
        primary_material=(
            ", ".join(str(item) for item in answers.get("8", []))
            if isinstance(answers.get("8"), list)
            else str(answers.get("8") or "") or None
        ),
        roof_material=str(answers.get("7") or "") or None,
        glazing=str(answers.get("9") or "") or None,
        lighting=str(answers.get("14") or "") or None,
        pbr_materials=PbrMaterialPalette(
            facade=_facade_preset(answers),
            roof=_roof_preset(answers),
            accent=AccentMaterialPreset.NATURAL_OAK,
            glazing=_glazing_preset(answers),
        ),
    )

    return ArchitecturePackage(
        program=HouseProgram(
            living_area_sqm=gross_area,
            storeys=level_count,
        ),
        geometry=HouseGeometry(
            levels=levels,
            roof=_roof(
                answers,
                level_count=level_count,
                width=width,
                depth=depth,
            ),
        ),
        appearance=appearance,
    )
