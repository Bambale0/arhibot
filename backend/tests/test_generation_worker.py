import pytest

from app.core.config import Settings
from app.workers.generation_worker import _download_image


@pytest.mark.asyncio
async def test_generated_image_download_requires_https() -> None:
    settings = Settings(
        jwt_secret="x" * 32,
        refresh_token_secret="y" * 32,
    )
    with pytest.raises(RuntimeError, match="must use HTTPS"):
        await _download_image("http://cdn.example.test/output.png", settings)


def test_questionnaire_aspect_ratio_inherits_source_shape() -> None:
    from types import SimpleNamespace

    from app.workers.generation_worker import _questionnaire_aspect_ratio

    assert _questionnaire_aspect_ratio(None) == "16:9"
    assert _questionnaire_aspect_ratio(SimpleNamespace(width=1920, height=1080)) == "16:9"
    assert _questionnaire_aspect_ratio(SimpleNamespace(width=2048, height=2048)) == "1:1"
    assert _questionnaire_aspect_ratio(SimpleNamespace(width=1200, height=1600)) == "3:4"
