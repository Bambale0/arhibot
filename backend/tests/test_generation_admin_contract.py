from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.admin import (
    AdminAiFlyoverGifCreate,
    AdminAiOrbitCreate,
    AdminAiSandboxCreate,
    GenerationRuntimeUpdate,
    PromptTemplateUpdate,
)


def test_generation_runtime_provider_defaults_use_neironych() -> None:
    payload = GenerationRuntimeUpdate(primary_model="existing-model")
    assert payload.primary_provider == "neironych"
    assert payload.fallback_provider == "neironych"


@pytest.mark.parametrize("field", ["primary_provider", "fallback_provider"])
@pytest.mark.parametrize("provider", ["unknown", "Nexus", "", None])
def test_generation_runtime_rejects_unknown_providers(field, provider) -> None:
    with pytest.raises(ValidationError):
        GenerationRuntimeUpdate(primary_model="model", **{field: provider})


@pytest.mark.parametrize("field", ["model", "images", "mask", "n", "response_format"])
@pytest.mark.parametrize("group", ["primary_params", "fallback_params", "mode_params"])
def test_generation_runtime_rejects_neironych_protocol_overrides(field, group) -> None:
    params = {field: "forged"}
    value = {"master_plan": params} if group == "mode_params" else params
    with pytest.raises(ValidationError, match="cannot override provider fields"):
        GenerationRuntimeUpdate(primary_model="model", **{group: value})
    assert params == {field: "forged"}


@pytest.mark.parametrize("field", ["model", "images", "mask", "n", "response_format"])
@pytest.mark.parametrize("schema", [AdminAiSandboxCreate, AdminAiOrbitCreate, AdminAiFlyoverGifCreate])
def test_admin_experiments_reject_neironych_protocol_overrides(schema, field) -> None:
    with pytest.raises(ValidationError, match="cannot override provider fields"):
        schema(
            model_name="model",
            prompt="A house",
            source_generation_id=uuid4(),
            params={field: "forged"},
        )


def test_generation_runtime_accepts_provider_routing_without_mutating_params() -> None:
    values = {
        "primary_provider": "neironych",
        "fallback_provider": "nexus",
        "primary_model": " image-model ",
        "primary_params": {"quality": "medium", "metadata": {"source": "admin"}},
        "mode_params": {"master_plan": {"size": "1536x1024"}},
    }
    payload = GenerationRuntimeUpdate.model_validate(values)
    assert payload.primary_provider == "neironych"
    assert payload.fallback_provider == "nexus"
    assert payload.primary_model == "image-model"
    assert values["primary_model"] == " image-model "
    assert values["primary_params"] == {"quality": "medium", "metadata": {"source": "admin"}}
    assert values["mode_params"] == {"master_plan": {"size": "1536x1024"}}


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
