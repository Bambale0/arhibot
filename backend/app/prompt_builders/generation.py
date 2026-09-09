from app.db.models.projects import Project


def build_project_context(project: Project) -> str:
    data = project.context or {}
    values = [
        f"{key}={value}"
        for key, value in data.items()
        if key != "design_session" and value not in (None, "")
    ]
    return ", ".join(values) if values else "not specified"


def build_generation_prompt(template: str, user_prompt: str, project: Project) -> str:
    """Render the operator-managed prompt template without Python format evaluation.

    Questionnaire answers are already rendered into user_prompt by the questionnaire
    flow, so design_session is intentionally excluded from generic project context.
    """
    return (
        template.replace("{project_context}", build_project_context(project))
        .replace("{user_prompt}", user_prompt.strip() or "not specified")
        .strip()
    )
