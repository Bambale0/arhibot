from uuid import uuid4

import pytest

from app.db.models.questionnaires import QuestionnaireApplication
from app.questionnaires.catalog import build_catalog
from app.telegram_bot.questionnaire_notifications import (
    _send_to_admins,
    build_application_message,
)


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



class _FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class _RetryingTelegramApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.failed_once = False

    def call(self, method: str, payload: dict, *, timeout: int = 15):
        self.calls.append((method, payload))
        if (
            method == "sendMessage"
            and payload["text"] == "chunk-2"
            and not self.failed_once
        ):
            self.failed_once = True
            raise RuntimeError("temporary Telegram failure")
        return {"message_id": len(self.calls)}


@pytest.mark.asyncio
async def test_questionnaire_delivery_resumes_after_partial_failure() -> None:
    application = QuestionnaireApplication(
        id=uuid4(),
        session_id=uuid4(),
        project_id=uuid4(),
        user_id=uuid4(),
        catalog_version="2026-09-10.1",
        selected_objects=["eskez-doma"],
        accepted_objects=["eskez-doma"],
        answers={},
        scene_asset_id=None,
        telegram_delivery_progress={},
    )
    session = _FakeSession()
    api = _RetryingTelegramApi()

    sent, errors = await _send_to_admins(
        api,
        ["12345"],
        ["chunk-1", "chunk-2", "chunk-3"],
        session=session,  # type: ignore[arg-type]
        application=application,
        photo_url="https://example.test/final.png",
    )
    assert sent == 0
    assert errors
    assert application.telegram_delivery_progress == {
        "12345": {"photo_sent": True, "chunks_sent": 1}
    }

    sent, errors = await _send_to_admins(
        api,
        ["12345"],
        ["chunk-1", "chunk-2", "chunk-3"],
        session=session,  # type: ignore[arg-type]
        application=application,
        photo_url="https://example.test/final.png",
    )
    assert sent == 1
    assert errors == []
    assert application.telegram_delivery_progress == {
        "12345": {"photo_sent": True, "chunks_sent": 3}
    }
    assert [method for method, _ in api.calls].count("sendPhoto") == 1
    sent_texts = [payload["text"] for method, payload in api.calls if method == "sendMessage"]
    assert sent_texts == ["chunk-1", "chunk-2", "chunk-2", "chunk-3"]
    assert session.commits == 4
