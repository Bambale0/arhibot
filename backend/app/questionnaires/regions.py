from collections.abc import Sequence

from app.schemas.generations import NormalizedRect
from app.schemas.questionnaires import DesignSession


def protected_object_keys(session: DesignSession, object_keys: Sequence[str]) -> list[str]:
    """Initial concepts have no object segmentation; guessed locks are not masks."""
    return [
        key
        for key in object_keys
        if key in session.lock_regions
        and (not session.initial_concept_mode or key in session.edit_regions)
    ]


def protected_object_regions(
    session: DesignSession, object_keys: Sequence[str]
) -> list[NormalizedRect]:
    regions = session.edit_regions if session.initial_concept_mode else session.lock_regions
    return [regions[key] for key in protected_object_keys(session, object_keys)]
