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
    assert set(IdeaPublicationCreate.model_fields) == {"generation_id"}
    assert set(IdeaPublicationUpdate.model_fields) == {"is_active", "sort_order"}
    public_fields = set(PublicIdeaPublicationResponse.model_fields)
    assert "prompt" not in public_fields
    assert "text" not in public_fields
    assert "media" not in public_fields
    assert "model_url" not in public_fields


def test_admin_idea_publication_order_is_bounded() -> None:
    with pytest.raises(ValidationError):
        IdeaPublicationUpdate(sort_order=100_001)
    assert IdeaPublicationCreate(generation_id=uuid4()).generation_id


def test_answer_text_is_user_facing() -> None:
    assert _answer_text(True) == "Да"
    assert _answer_text(False) == "Нет"
    assert _answer_text(["Кирпич", "Дерево"]) == "Кирпич, Дерево"
    assert _answer_text(None) == ""


def test_repeat_idea_recovers_legacy_design_answers_without_contact_or_review():
    from app.questionnaires.catalog import build_catalog
    from app.questionnaires.idea_template import design_answers_from_snapshot
    from app.services.questionnaire_service import QuestionnaireService
    catalog = build_catalog()
    snapshot = {'objects': [{'key': 'eskez-doma', 'answers': [
        {'question': 'Какой стиль вам нравится?', 'answer': 'Барнхаус'},
        {'question': 'Номер телефона', 'answer': '+70000000000'},
    ]}], 'design_template': {'answers': [
        {'object_key': 'zayavka', 'question': 'Номер телефона', 'value': '+70000000000'},
    ]}}
    result = design_answers_from_snapshot(snapshot, catalog, ['eskez-doma'], QuestionnaireService(None)._validate_answer)
    assert result == {'eskez-doma': {'1': 'Барнхаус'}}


def test_legacy_multiselect_preserves_options_with_commas_in_any_order():
    from app.questionnaires.idea_template import _legacy_value
    question={'kind':'multi','options':['Газон','Цветники, клумбы','Хвойные']}
    assert _legacy_value(question,'Газон, Цветники, клумбы') == ['Газон','Цветники, клумбы']
    assert _legacy_value(question,'Цветники, клумбы, Газон') == ['Цветники, клумбы','Газон']
    assert _legacy_value(question,'Неизвестное') is None


def test_template_rejects_catalog_drift_non_design_and_nonfinite_values():
    from app.questionnaires.catalog import build_catalog, user_question_title
    from app.questionnaires.idea_template import design_answers_from_snapshot
    from app.services.questionnaire_service import QuestionnaireService
    catalog=build_catalog();house=next(d for d in catalog['questionnaires'] if d['key']=='eskez-doma')
    area=next(q for q in house['questions'] if q['id']=='3')
    snapshot={'objects':[None,{'key':'eskez-doma','answers':['bad']}], 'design_template':{'answers':[
        {'object_key':'eskez-doma','question':user_question_title(area['text']),'value':float('inf')},
        {'object_key':'eskez-doma','question':'Какой стиль вам нравится?','value':'removed-catalog-option'},
    ]}}
    assert design_answers_from_snapshot(snapshot,catalog,['eskez-doma'],QuestionnaireService(None)._validate_answer) == {}
