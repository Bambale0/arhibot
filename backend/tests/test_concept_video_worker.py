from uuid import uuid4

import pytest

from app.db.models.generations import Generation
from app.domain.generations.enums import GenerationOrigin, GenerationType
from app.workers.generation_worker import (
    _concept_video_dimensions,
    _concept_video_end_frame_prompt,
    _concept_video_end_frame_retry_prompt,
    _concept_video_request,
)


def _generation(source_id):
    return Generation(
        id=uuid4(),
        user_id=uuid4(),
        project_id=uuid4(),
        input_asset_id=uuid4(),
        type=GenerationType.VIDEO,
        origin=GenerationOrigin.QUESTIONNAIRE_VIDEO.value,
        prompt=(
            "AUROOM_CONCEPT_VIDEO_V1\n"
            + '{"source_generation_id":"' + str(source_id) + '"}'
        ),
    )


def test_concept_video_envelope_binds_source_generation() -> None:
    source_id = uuid4()
    assert _concept_video_request(_generation(source_id)) == source_id


def test_concept_video_end_frame_prompt_moves_camera_only() -> None:
    prompt = _concept_video_end_frame_prompt("AUROOM_INITIAL_CONCEPT_V1\nCANONICAL")
    assert "CAMERA MOVE ONLY" in prompt
    assert "Do not add, remove, redesign or relocate anything" in prompt
    assert "about 6 degrees" in prompt
    assert "do not pull back" in prompt
    assert "AUROOM_INITIAL_CONCEPT_V1" in prompt


def test_concept_video_retry_prompt_uses_grok_differences_and_tightens_camera_move() -> None:
    prompt = _concept_video_end_frame_retry_prompt(
        "AUROOM_INITIAL_CONCEPT_V1\nCANONICAL",
        [
            "Roof geometry changed",
            "A swimming pool was added",
        ],
    )

    assert "CORRECTIVE RETRY" in prompt
    assert "Roof geometry changed" in prompt
    assert "A swimming pool was added" in prompt
    assert "about 3 degrees" in prompt
    assert "reference image 1" in prompt
    assert "AUROOM_INITIAL_CONCEPT_V1" in prompt


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"resolution": "1080p", "aspect_ratio": "16:9"}, (1920, 1080)),
        ({"resolution": "720p", "aspect_ratio": "9:16"}, (720, 1280)),
        ({"resolution": "4k", "aspect_ratio": "16:9"}, (3840, 2160)),
    ],
)
def test_concept_video_dimensions_follow_seedance_output(params, expected) -> None:
    assert _concept_video_dimensions(params) == expected
