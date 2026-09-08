import pytest
from pydantic import ValidationError

from app.schemas.admin import IdeaCreate, IdeaMediaInput


def test_idea_media_label_is_trimmed() -> None:
    media = IdeaMediaInput(
        asset_id="00000000-0000-0000-0000-000000000001", kind="reference", label="  Stone facade  "
    )
    assert media.label == "Stone facade"


def test_idea_media_is_bounded() -> None:
    media = [
        {
            "asset_id": f"00000000-0000-0000-0000-{index:012d}",
            "kind": "photo",
            "label": f"Photo {index}",
        }
        for index in range(25)
    ]
    with pytest.raises(ValidationError):
        IdeaCreate(
            title="Too many files",
            category="Facade",
            text="Media bound",
            generation_type="facade",
            media=media,
        )
