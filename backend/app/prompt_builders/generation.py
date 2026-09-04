from app.db.models.projects import Project
from app.domain.generations.enums import GenerationType


BASE_INSTRUCTION = (
    "Create a realistic, professional architectural visualization. Preserve useful geometry "
    "from the reference image unless the scenario explicitly requires a new plan. No text, "
    "logos, watermarks, UI, people, or decorative labels."
)

MODE_INSTRUCTIONS: dict[GenerationType, str] = {
    GenerationType.FLOOR_PLAN: (
        "Create a clean top-down residential floor plan concept. Prioritize functional zoning, "
        "comfortable circulation, realistic room proportions, daylight access and buildable logic."
    ),
    GenerationType.FACADE: (
        "Redesign the exterior facade of the referenced house while preserving its main massing, "
        "openings and camera viewpoint. Produce a photorealistic architectural exterior."
    ),
    GenerationType.MASTER_PLAN: (
        "Create a coherent top-down master plan for the site: house placement, access, parking, "
        "paths, private outdoor zones and landscaping. Keep the result visually clear and realistic."
    ),
    GenerationType.INTERIOR: (
        "Redesign the referenced room while preserving its structural geometry and camera viewpoint. "
        "Produce a photorealistic interior with practical furniture placement and realistic lighting."
    ),
}


def build_generation_prompt(generation_type: GenerationType, user_prompt: str, project: Project) -> str:
    context: list[str] = []
    data = project.context or {}
    labels = {
        "house_area_m2": "house area m2",
        "floors": "floors",
        "plot_area_m2": "plot area m2",
        "bedrooms": "bedrooms",
        "bathrooms": "bathrooms",
        "architecture_style": "architecture style",
    }
    for key, label in labels.items():
        value = data.get(key)
        if value not in (None, ""):
            context.append(f"{label}: {value}")

    parts = [BASE_INSTRUCTION, MODE_INSTRUCTIONS[generation_type]]
    if context:
        parts.append("Project context: " + ", ".join(context) + ".")
    if user_prompt.strip():
        parts.append("Client preferences: " + user_prompt.strip())
    return "\n\n".join(parts)
