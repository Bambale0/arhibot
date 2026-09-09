import pytest
from pydantic import ValidationError

from app.domain.generations.enums import GenerationType
from app.schemas.generations import GenerationCreate


def test_masked_generation_requires_input_and_edit_region() -> None:
    with pytest.raises(ValidationError, match="input image"):
        GenerationCreate(
            project_id="00000000-0000-0000-0000-000000000001",
            type=GenerationType.MASTER_PLAN,
            prompt="add a bathhouse",
            composition_mode="masked_edit",
            edit_region={"x": 0.5, "y": 0.2, "width": 0.4, "height": 0.6},
        )

    with pytest.raises(ValidationError, match="edit region"):
        GenerationCreate(
            project_id="00000000-0000-0000-0000-000000000001",
            input_asset_id="00000000-0000-0000-0000-000000000002",
            type=GenerationType.MASTER_PLAN,
            prompt="add a bathhouse",
            composition_mode="masked_edit",
        )


def test_replace_generation_cannot_smuggle_mask_regions() -> None:
    with pytest.raises(ValidationError, match="require masked_edit"):
        GenerationCreate(
            project_id="00000000-0000-0000-0000-000000000001",
            input_asset_id="00000000-0000-0000-0000-000000000002",
            type=GenerationType.MASTER_PLAN,
            prompt="replace",
            edit_region={"x": 0.1, "y": 0.1, "width": 0.4, "height": 0.4},
        )


def test_normalized_region_must_stay_inside_image() -> None:
    with pytest.raises(ValidationError, match="stay inside"):
        GenerationCreate(
            project_id="00000000-0000-0000-0000-000000000001",
            input_asset_id="00000000-0000-0000-0000-000000000002",
            type=GenerationType.MASTER_PLAN,
            prompt="add object",
            composition_mode="masked_edit",
            edit_region={"x": 0.8, "y": 0.2, "width": 0.4, "height": 0.5},
        )
