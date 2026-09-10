from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.admin import (
    IdeaPublicationCreate,
    IdeaPublicationUpdate,
    PublicIdeaPublicationResponse,
)
from app.services.idea_service import _answer_text


def test_idea_publication_contract_has_no_parallel_prompt_or_media_editor() -> None:
    assert set(IdeaPublicationCreate.model_fields) == {"generation_id", "is_active", "sort_order"}
    assert set(IdeaPublicationUpdate.model_fields) == {"is_active", "sort_order"}
    public_fields = set(PublicIdeaPublicationResponse.model_fields)
    assert "prompt" not in public_fields
    assert "text" not in public_fields
    assert "media" not in public_fields
    assert "model_url" not in public_fields


def test_idea_publication_order_is_bounded() -> None:
    with pytest.raises(ValidationError):
        IdeaPublicationCreate(generation_id=uuid4(), sort_order=100_001)


def test_answer_text_is_user_facing() -> None:
    assert _answer_text(True) == "Да"
    assert _answer_text(False) == "Нет"
    assert _answer_text(["Кирпич", "Дерево"]) == "Кирпич, Дерево"
    assert _answer_text(None) == ""
