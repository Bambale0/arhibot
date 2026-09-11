from io import BytesIO
from urllib.parse import parse_qs, urlsplit

from PIL import Image

from app.api.v1.media import (
    TELEGRAM_PREVIEW_MAX_BYTES,
    TELEGRAM_PREVIEW_MAX_SIDE,
    _telegram_preview,
)
from app.core.config import Settings
from app.services.asset_service import LocalMediaStorage


def _settings(tmp_path) -> Settings:
    return Settings(
        jwt_secret="x" * 32,
        refresh_token_secret="y" * 32,
        media_signing_secret="z" * 32,
        media_root=str(tmp_path),
        media_public_base_url="https://media.example.test",
    )


def test_telegram_preview_is_jpeg_and_bounded(tmp_path) -> None:
    source = tmp_path / "large.png"
    image = Image.effect_noise((3200, 2200), 100).convert("RGB")
    image.save(source, format="PNG")

    data = _telegram_preview(source)

    assert len(data) <= TELEGRAM_PREVIEW_MAX_BYTES
    with Image.open(BytesIO(data)) as preview:
        assert preview.format == "JPEG"
        assert preview.mode == "RGB"
        assert max(preview.size) <= TELEGRAM_PREVIEW_MAX_SIDE


def test_telegram_photo_url_reuses_signed_media_contract(tmp_path) -> None:
    storage = LocalMediaStorage(_settings(tmp_path))
    path = "users/test/result.png"
    target = storage.absolute_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"placeholder")

    url = storage.signed_telegram_photo_url(path, ttl_seconds=300)
    query = parse_qs(urlsplit(url).query)

    assert query["preview"] == ["telegram"]
    assert "expires" in query
    assert "signature" in query
