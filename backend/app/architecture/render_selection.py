from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.architecture.enums import ArchitectureCameraProfile

_CAMERA_PRIORITY = {
    ArchitectureCameraProfile.HERO_CORNER: 0,
    ArchitectureCameraProfile.REVERSE_CORNER: 1,
    ArchitectureCameraProfile.ELEVATED: 2,
}


@dataclass(frozen=True, slots=True)
class RenderCandidate:
    render_id: UUID
    camera_profile: ArchitectureCameraProfile
    quality_score: float
    technically_usable: bool


def choose_batch_winner(candidates: list[RenderCandidate]) -> RenderCandidate | None:
    if not candidates:
        return None

    return max(
        candidates,
        key=lambda candidate: (
            candidate.technically_usable,
            candidate.quality_score,
            -_CAMERA_PRIORITY[candidate.camera_profile],
        ),
    )
