from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.telegram_bot.main import canonicalize_webapp_url

_NAVIGATION_KEYS = {
    "admin",
    "application",
    "billing",
    "generation",
    "idea",
    "project",
    "user",
}


def webapp_deep_link(webapp_url: str, **params: object | None) -> str:
    safe = canonicalize_webapp_url(webapp_url)
    parsed = urlsplit(safe)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in _NAVIGATION_KEYS
    ]
    query.extend(
        (key, str(value))
        for key, value in params.items()
        if key in _NAVIGATION_KEYS and value is not None
    )
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query),
            parsed.fragment,
        )
    )


def admin_application_keyboard(
    webapp_url: str,
    *,
    application_id: object,
    user_id: object,
    telegram_user_id: str | None,
) -> dict:
    rows = [
        [
            {
                "text": "Заявка в админке",
                "web_app": {
                    "url": webapp_deep_link(
                        webapp_url,
                        admin=1,
                        application=application_id,
                    )
                },
            }
        ],
        [
            {
                "text": "Профиль клиента",
                "web_app": {
                    "url": webapp_deep_link(
                        webapp_url,
                        admin=1,
                        user=user_id,
                    )
                },
            }
        ],
    ]
    if telegram_user_id and telegram_user_id.isdigit():
        rows.append(
            [
                {
                    "text": "Telegram профиль",
                    "url": f"tg://user?id={telegram_user_id}",
                }
            ]
        )
    return {"inline_keyboard": rows}
