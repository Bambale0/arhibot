from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image

from app.core.config import Settings
from app.core.cursor import decode_cursor, encode_cursor
from app.core.errors import AppError
from app.services.asset_service import AssetService, LocalMediaStorage


class DummyRepository:
    session = None


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        media_root=str(tmp_path / "media"),
        media_public_base_url="https://media.example.test",
        max_image_size_bytes=2 * 1024 * 1024,
        max_image_pixels=20_000_000,
    )


def png_bytes(width: int = 32, height: int = 24) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_cursor_round_trip() -> None:
    created_at = datetime(2026, 9, 3, 12, 30, tzinfo=UTC)
    item_id = uuid4()
    cursor = encode_cursor(created_at, item_id)
    assert decode_cursor(cursor) == (created_at, item_id)


def test_invalid_cursor_has_api_error() -> None:
    with pytest.raises(AppError) as exc:
        decode_cursor("not-a-cursor")
    assert exc.value.type == "invalid_cursor"
    assert exc.value.status == 422


def test_image_validation_detects_real_type(settings: Settings) -> None:
    service = AssetService(DummyRepository(), DummyRepository(), settings)
    image = service._validate_image(png_bytes())
    assert image.mime_type == "image/png"
    assert image.extension == "png"
    assert (image.width, image.height) == (32, 24)


def test_invalid_image_is_rejected(settings: Settings) -> None:
    service = AssetService(DummyRepository(), DummyRepository(), settings)
    with pytest.raises(AppError) as exc:
        service._validate_image(b"this is not an image")
    assert exc.value.type == "invalid_image"


@pytest.mark.asyncio
async def test_local_media_storage_writes_under_root(settings: Settings) -> None:
    storage = LocalMediaStorage(settings)
    relative = "users/abc/2026/09/file.png"
    await storage.write(relative, b"payload")
    assert storage.absolute_path(relative).read_bytes() == b"payload"
    assert storage.public_url(relative) == "https://media.example.test/uploads/users/abc/2026/09/file.png"


def test_local_media_storage_blocks_path_escape(settings: Settings) -> None:
    storage = LocalMediaStorage(settings)
    with pytest.raises(ValueError):
        storage.absolute_path("../../etc/passwd")
