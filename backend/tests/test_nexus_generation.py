from app.db.models.projects import Project
from app.domain.generations.enums import GenerationType
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


def test_facade_prompt_contains_project_context_and_client_preferences() -> None:
    project = Project(
        name="House",
        context={
            "house_area_m2": 180,
            "floors": 2,
            "architecture_style": "minimalism",
        },
    )
    prompt = build_generation_prompt(
        GenerationType.FACADE,
        "warm stone and timber",
        project,
    )

    assert "exterior facade" in prompt
    assert "house area m2: 180" in prompt
    assert "architecture style: minimalism" in prompt
    assert "warm stone and timber" in prompt
