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
