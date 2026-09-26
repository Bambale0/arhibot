from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.db.models.generations import Generation
from app.db.models.projects import Project
from app.questionnaires.catalog import build_catalog, user_question_title
from app.questionnaires.idea_template import design_answers_from_snapshot
from app.schemas.questionnaires import DesignSession
from app.services.idea_service import IdeaService
from app.services.questionnaire_service import QuestionnaireService


@pytest.mark.parametrize("empty_questions", [("11",), ("13",), ("11", "13")])
async def test_published_snapshot_repeats_explicit_empty_choices_without_inventing_answers(
    monkeypatch, empty_questions,
):
    catalog = build_catalog()
    monkeypatch.setattr(
        QuestionnaireService, "catalog_for_version", AsyncMock(return_value=catalog),
    )
    generation = Generation(id=uuid4())
    expected_answers = {"1": "Современный минимализм", **{key: [] for key in empty_questions}}
    state = DesignSession(
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma"],
        accepted_objects=["eskez-doma"],
        generation_ids={"eskez-doma": generation.id},
        plot_area_sotkas=10,
        answers={
            "eskez-doma": {**expected_answers, "15": "Да, идём дальше"},
            "zayavka": {"1": "Private owner contact"},
        },
    )
    project = Project(
        name="Published house", context={"design_session": state.model_dump(mode="json")},
    )
    service = IdeaService(None, Settings(_env_file=None))

    snapshot = await service._build_snapshot(project, generation)
    repeated = design_answers_from_snapshot(
        snapshot, catalog, ["eskez-doma"], QuestionnaireService(None)._validate_answer,
    )

    assert repeated == {"eskez-doma": expected_answers}
    house = next(item for item in catalog["questionnaires"] if item["key"] == "eskez-doma")
    titles = {
        question["id"]: user_question_title(question["text"]) for question in house["questions"]
    }
    assert snapshot["design_template"] == {
        "plot_area_sotkas": 10,
        "answers": [
            {"object_key": "eskez-doma", "question": titles[key], "value": value}
            for key, value in expected_answers.items()
        ],
    }
    # Empty choices remain meaningful template values, without blank public rows.
    assert snapshot["objects"][0]["answers"] == [
        {"question": titles["1"], "answer": "Современный минимализм"},
    ]
