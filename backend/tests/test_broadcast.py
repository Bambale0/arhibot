from app.telegram_bot.broadcast import send_broadcast


class FakeApi:
    def __init__(self, fail_for: set[str] | None = None) -> None:
        self.fail_for = fail_for or set()
        self.calls: list[tuple[str, dict]] = []

    def call(self, method: str, payload: dict, **_: object) -> object:
        self.calls.append((method, payload))
        if str(payload.get("chat_id")) in self.fail_for:
            raise RuntimeError("telegram failed")
        return True


def test_send_broadcast_sends_to_every_recipient() -> None:
    api = FakeApi()
    sent, failed = send_broadcast(api, ["1", "2"], "AuRoom update")

    assert (sent, failed) == (2, 0)
    assert api.calls == [
        ("sendMessage", {"chat_id": "1", "text": "AuRoom update"}),
        ("sendMessage", {"chat_id": "2", "text": "AuRoom update"}),
    ]


def test_send_broadcast_counts_failures_and_continues() -> None:
    api = FakeApi({"2"})
    sent, failed = send_broadcast(api, ["1", "2", "3"], "Hello")

    assert (sent, failed) == (2, 1)
    assert len(api.calls) == 3
