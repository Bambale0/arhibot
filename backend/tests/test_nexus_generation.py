from app.db.models.projects import Project
from app.prompt_builders.generation import build_generation_prompt
from app.providers.nexus import NexusImageProvider


def test_nexus_extracts_image_url_from_result_list() -> None:
    url = NexusImageProvider._extract_image_url(
        {"status": "completed"},
        {"image_urls": ["https://cdn.example.com/result.png"]},
    )
    assert url == "https://cdn.example.com/result.png"


def test_nexus_extracts_top_level_image_url() -> None:
    url = NexusImageProvider._extract_image_url(
        {"status": "completed", "image_url": "https://cdn.example.com/result.webp"},
        {},
    )
    assert url == "https://cdn.example.com/result.webp"


def test_admin_prompt_template_renders_project_context_and_client_preferences() -> None:
    project = Project(
        name="House",
        context={
            "house_area_m2": 180,
            "floors": 2,
            "architecture_style": "minimalism",
        },
    )
    template = (
        "Create exterior facade.\n"
        "Project context: {project_context}\n"
        "Client preferences: {user_prompt}"
    )
    prompt = build_generation_prompt(template, "warm stone and timber", project)

    assert "Create exterior facade" in prompt
    assert "house_area_m2=180" in prompt
    assert "architecture_style=minimalism" in prompt
    assert "warm stone and timber" in prompt


def test_nexus_model_params_cannot_override_prompt_model_or_reference() -> None:
    params = NexusImageProvider._build_params(
        model_name="real-model",
        prompt="canonical prompt",
        image_url="https://media.example.com/base.png",
        model_params={
            "model_name": "forged-model",
            "prompt": "forged prompt",
            "image_urls": ["https://evil.example.com/other.png"],
            "steps": 24,
        },
    )

    assert params["model_name"] == "real-model"
    assert params["prompt"] == "canonical prompt"
    assert params["image_urls"] == ["https://media.example.com/base.png"]
    assert params["steps"] == 24
