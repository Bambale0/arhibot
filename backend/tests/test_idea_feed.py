import json
import struct

import pytest
from pydantic import ValidationError

from app.core.errors import AppError
from app.schemas.admin import IdeaCreate, IdeaMediaInput
from app.services.idea_service import validate_glb


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


def _glb(document: dict) -> bytes:
    payload = json.dumps(document, separators=(",", ":")).encode("utf-8")
    payload += b" " * ((4 - len(payload) % 4) % 4)
    total = 12 + 8 + len(payload)
    header = struct.pack("<4sII", b"glTF", 2, total)
    json_chunk = struct.pack("<II", len(payload), 0x4E4F534A) + payload
    return header + json_chunk


def test_glb_validation_accepts_self_contained_gltf2() -> None:
    document = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": []}], "nodes": []}
    assert validate_glb(_glb(document), max_size_bytes=1024 * 1024)["asset"]["version"] == "2.0"


def test_glb_validation_rejects_external_resources() -> None:
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"uri": "mesh.bin", "byteLength": 4}],
    }
    with pytest.raises(AppError) as exc:
        validate_glb(_glb(document), max_size_bytes=1024 * 1024)
    assert exc.value.type == "external_idea_model_resource"
