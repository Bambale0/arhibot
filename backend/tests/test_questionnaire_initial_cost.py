import pytest

from app.api.v1.questionnaires import get_questionnaire_generation_cost
from app.schemas.questionnaires import QuestionnaireGenerationCostResponse
from app.services.questionnaire_service import QuestionnaireService


@pytest.mark.asyncio
async def test_initial_questionnaire_concept_reports_zero_credits_when_generation_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def configured_cost(self, user):  # noqa: ANN001
        return QuestionnaireGenerationCostResponse(
            generation_type="master_plan",
            credits=7,
            is_available=True,
        )

    monkeypatch.setattr(QuestionnaireService, "generation_cost", configured_cost)

    response = await get_questionnaire_generation_cost(object(), object())  # type: ignore[arg-type]

    assert response.generation_type == "master_plan"
    assert response.is_available is True
    assert response.credits == 0


@pytest.mark.asyncio
async def test_initial_questionnaire_cost_keeps_unavailable_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable_cost(self, user):  # noqa: ANN001
        return QuestionnaireGenerationCostResponse(
            generation_type="master_plan",
            credits=None,
            is_available=False,
        )

    monkeypatch.setattr(QuestionnaireService, "generation_cost", unavailable_cost)

    response = await get_questionnaire_generation_cost(object(), object())  # type: ignore[arg-type]

    assert response.is_available is False
    assert response.credits is None
