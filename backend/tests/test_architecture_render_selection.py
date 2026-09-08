from uuid import uuid4

from app.architecture.render_selection import RenderCandidate, choose_batch_winner
from app.domain.architecture.enums import ArchitectureCameraProfile


def _candidate(
    camera: ArchitectureCameraProfile,
    score: float,
    *,
    usable: bool,
) -> RenderCandidate:
    return RenderCandidate(
        render_id=uuid4(),
        camera_profile=camera,
        quality_score=score,
        technically_usable=usable,
    )


def test_batch_winner_prefers_technically_usable_render() -> None:
    unusable = _candidate(ArchitectureCameraProfile.HERO_CORNER, 0.99, usable=False)
    usable = _candidate(ArchitectureCameraProfile.REVERSE_CORNER, 0.61, usable=True)

    winner = choose_batch_winner([unusable, usable])

    assert winner is usable


def test_batch_winner_uses_quality_score_then_camera_priority() -> None:
    hero = _candidate(ArchitectureCameraProfile.HERO_CORNER, 0.8, usable=True)
    reverse = _candidate(ArchitectureCameraProfile.REVERSE_CORNER, 0.8, usable=True)
    elevated = _candidate(ArchitectureCameraProfile.ELEVATED, 0.9, usable=True)

    assert choose_batch_winner([hero, reverse]) is hero
    assert choose_batch_winner([hero, reverse, elevated]) is elevated


def test_batch_winner_returns_none_without_completed_candidates() -> None:
    assert choose_batch_winner([]) is None
