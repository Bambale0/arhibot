import pytest

from app.api.v1.questionnaires import get_questionnaire_generation_cost
from app.schemas.questionnaires import QuestionnaireGenerationCostResponse
from app.services.questionnaire_service import QuestionnaireService


@pytest.mark.asyncio
async def test_initial_questionnaire_concept_reports_configured_credits_when_generation_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def configured_cost(self, user, project_id=None):  # noqa: ANN001
        return QuestionnaireGenerationCostResponse(
            generation_type="master_plan",
            initial_credits=2,
            credits=7,
            initial_offer_available=True,
            is_available=True,
        )

    monkeypatch.setattr(QuestionnaireService, "generation_cost", configured_cost)

    response = await get_questionnaire_generation_cost(object(), object(), None)  # type: ignore[arg-type]

    assert response.generation_type == "master_plan"
    assert response.is_available is True
    assert response.initial_credits == 2
    assert response.credits == 7


@pytest.mark.asyncio
async def test_initial_questionnaire_cost_keeps_unavailable_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable_cost(self, user, project_id=None):  # noqa: ANN001
        return QuestionnaireGenerationCostResponse(
            generation_type="master_plan",
            credits=None,
            is_available=False,
        )

    monkeypatch.setattr(QuestionnaireService, "generation_cost", unavailable_cost)

    response = await get_questionnaire_generation_cost(object(), object(), None)  # type: ignore[arg-type]

    assert response.is_available is False
    assert response.initial_credits == 0
    assert response.credits is None
