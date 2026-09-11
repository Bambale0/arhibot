from uuid import uuid4

from app.db.models.questionnaires import QuestionnaireApplication
from app.questionnaires.catalog import build_catalog
from app.telegram_bot.questionnaire_notifications import build_application_message


def test_questionnaire_application_message_contains_admin_lead_data() -> None:
    catalog = build_catalog()
    house = next(item for item in catalog["questionnaires"] if item["key"] == "eskez-doma")
    house_style = next(question for question in house["questions"] if question["id"] == "1")

    application = QuestionnaireApplication(
        id=uuid4(),
        session_id=uuid4(),
        project_id=uuid4(),
        user_id=uuid4(),
        catalog_version="2026-09-09.1",
        selected_objects=["eskez-doma", "banya"],
        accepted_objects=["eskez-doma"],
        answers={
            "eskez-doma": {"1": house_style["options"][0]},
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
        catalog=catalog,
    )

    assert "Новая заявка AuRoom" in message
    assert "Проект: Дом у озера" in message
    assert "Клиент: Иван Петров" in message
    assert "Принятые объекты: Дом, фасад" in message
    assert "Контакт: +79990000000" in message
    assert "Согласие ПД: Да" in message
    assert "Архитектурный бриф" in message
    assert house_style["text"] in message
    assert house_style["options"][0] in message
    assert "Финальный эскиз asset:" in message
    assert str(application.id) in message
