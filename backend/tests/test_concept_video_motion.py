from app.workers.generation_worker import _concept_video_motion_prompt


def test_concept_video_motion_prompt_uses_safe_cinematic_parallax() -> None:
    prompt = _concept_video_motion_prompt().lower()

    assert "accepted start still is the ground truth" in prompt
    assert "slow stabilized forward dolly" in prompt
    assert "small lateral truck" in prompt
    assert "slight camera rise" in prompt
    assert "constant focal length" in prompt
    assert "ease-in" in prompt and "ease-out" in prompt
    assert "do not orbit" in prompt
    assert "do not pass over the roof" in prompt
    assert "unseen" in prompt and "reduce the apparent parallax" in prompt
    assert "camera motion only" in prompt
    assert "drone flyover" not in prompt


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
