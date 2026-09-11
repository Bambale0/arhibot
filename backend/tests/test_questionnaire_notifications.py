from uuid import uuid4

from app.db.models.questionnaires import QuestionnaireApplication
from app.questionnaires.catalog import build_catalog
from app.telegram_bot.questionnaire_notifications import build_application_message, build_application_messages


def test_questionnaire_application_message_contains_admin_lead_data() -> None:
    application = QuestionnaireApplication(
        id=uuid4(),
        session_id=uuid4(),
        project_id=uuid4(),
        user_id=uuid4(),
        catalog_version="2026-09-09.1",
        selected_objects=["eskez-doma", "banya"],
        accepted_objects=["eskez-doma"],
        answers={
            "eskez-doma": {
                "1": "Современный минимализм",
            },
            "zayavka": {
                "20": "Участок есть",
                "21": "10–20 млн ₽",
                "22": "В этом году",
                "23": "Иван",
                "24": "+79990000000",
                "25": True,
            }
        },
        scene_asset_id=None,
    )

    message = build_application_message(
        application,
        project_name="Дом у озера",
        user_name="Иван Петров",
    )

    assert "Новая заявка AuRoom" in message
    assert "Проект: Дом у озера" in message
    assert "Клиент: Иван Петров" in message
    assert "Принятые объекты: Дом, фасад" in message
    assert "Контакт: +79990000000" in message
    assert "Согласие ПД: Да" in message
    assert str(application.id) in message


def test_questionnaire_application_messages_include_resolved_architectural_brief() -> None:
    catalog = build_catalog()
    application = QuestionnaireApplication(
        id=uuid4(),
        session_id=uuid4(),
        project_id=uuid4(),
        user_id=uuid4(),
        catalog_version=catalog["version"],
        selected_objects=["eskez-doma"],
        accepted_objects=["eskez-doma"],
        answers={
            "eskez-doma": {"1": "Современный минимализм"},
            "zayavka": {
                "20": "Участок есть",
                "21": "10–20 млн ₽",
                "22": "В этом году",
                "23": "Иван",
                "24": "@ivan",
                "25": True,
            },
        },
        scene_asset_id=uuid4(),
    )

    messages = build_application_messages(
        application,
        catalog=catalog,
        project_name="Дом у озера",
        user_name="Иван Петров",
    )

    assert len(messages) >= 2
    brief = "\n".join(messages[1:])
    assert "Архитектурный бриф" in brief
    assert "Дом, фасад" in brief
    assert "Какой стиль вам нравится?" in brief
    assert "Современный минимализм" in brief
    assert all(len(message) <= 3800 for message in messages)
