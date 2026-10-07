from app.workers.generation_worker import _concept_video_motion_prompt


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
