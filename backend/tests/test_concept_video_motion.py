from app.workers.generation_worker import (
    CONCEPT_VIDEO_MOTION_PROFILE,
    _concept_video_motion_profile_for_request,
    _concept_video_motion_prompt,
)


def test_concept_video_motion_prompt_uses_bounded_bird_flyover() -> None:
    prompt = _concept_video_motion_prompt().lower()

    assert "accepted start still is the ground truth" in prompt
    assert "bird" in prompt
    assert "camera rise" in prompt
    assert "arc" in prompt
    assert "20" in prompt and "35" in prompt and "45" in prompt
    assert "currently visible" in prompt
    assert "rear facade" in prompt
    assert "reduce the arc" in prompt
    assert "constant focal length" in prompt
    assert "ease-in" in prompt and "ease-out" in prompt
    assert "camera motion only" in prompt
    assert "start frame" in prompt
    assert "end frame" not in prompt
    assert "do not orbit" not in prompt


def test_concept_video_motion_prompt_locks_scene_and_lighting() -> None:
    prompt = _concept_video_motion_prompt().lower()

    for token in (
        "roof",
        "windows",
        "doors",
        "terraces",
        "pool",
        "paths",
        "fence",
        "materials",
        "object count",
    ):
        assert token in prompt

    assert "no relighting" in prompt
    assert "no weather change" in prompt
    assert "no vegetation animation" in prompt
    assert "no moving water" in prompt
    assert "no people" in prompt
    assert "no vehicles" in prompt


def test_concept_video_motion_prompt_stages_real_architectural_overview() -> None:
    prompt = _concept_video_motion_prompt().lower()

    # Duration-independent staging: the admin may change video duration.
    for stage in ("first quarter", "middle half", "final quarter"):
        assert stage in prompt

    # Physically moving the camera must dominate digital enlargement.
    assert "noticeable camera rise" in prompt
    assert "lateral truck" in prompt
    assert "house centered" in prompt
    assert "not a push-in" in prompt
    assert "not a digital zoom" in prompt
    assert "parallax" in prompt
    assert "more of the roof and site" in prompt


def test_concept_video_motion_prompt_preserves_framing_as_camera_rises() -> None:
    prompt = _concept_video_motion_prompt().lower()

    assert "original accepted viewpoint" in prompt
    assert "keep the entire house in frame" in prompt
    assert "no abrupt camera cuts" in prompt
    assert "rear facade" in prompt
    assert "reduce the arc" in prompt
    assert "constant focal length" in prompt


def test_motion_profile_keeps_original_version_for_inflight_video() -> None:
    old_report = {
        "video_motion_profile": "bird_flyover_safe_v2",
        "video_request": {
            "state": "accepted",
            "request_body": '{"model":"seedance-2.5","prompt":"original video prompt"}',
            "request_id": "previous-provider-request",
        },
    }

    assert _concept_video_motion_profile_for_request(old_report) == "bird_flyover_safe_v2"
    assert _concept_video_motion_profile_for_request(
        {"video_request": {"request_body": '{"model":"seedance-2.5"}'}}
    ) == "legacy_unversioned_request"


def test_motion_profile_uses_new_version_for_fresh_requests() -> None:
    assert _concept_video_motion_profile_for_request({}) == CONCEPT_VIDEO_MOTION_PROFILE
    assert _concept_video_motion_profile_for_request(
        {"video_request": {"state": "prepared"}}
    ) == CONCEPT_VIDEO_MOTION_PROFILE
