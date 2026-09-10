import pytest
from pydantic import ValidationError

from app.schemas.admin import GenerationRuntimeUpdate, PromptTemplateUpdate


def test_generation_runtime_rejects_provenance_field_overrides() -> None:
    with pytest.raises(ValidationError, match="cannot override provider fields"):
        GenerationRuntimeUpdate(
            primary_model="model",
            primary_params={"prompt": "forged", "steps": 20},
        )

    with pytest.raises(ValidationError, match="cannot override provider fields"):
        GenerationRuntimeUpdate(
            primary_model="model",
            mode_params={"master_plan": {"image_urls": ["https://example.test/forged.png"]}},
        )


def test_generation_prompt_template_must_include_questionnaire_prompt() -> None:
    with pytest.raises(ValidationError, match="user_prompt"):
        PromptTemplateUpdate(template="Render a beautiful architecture image")

    payload = PromptTemplateUpdate(template="Render carefully. {user_prompt}")
    assert payload.template == "Render carefully. {user_prompt}"
