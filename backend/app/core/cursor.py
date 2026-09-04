import base64
import json
from datetime import datetime
from uuid import UUID

from app.core.errors import AppError


def encode_cursor(created_at: datetime, item_id: UUID) -> str:
    raw = json.dumps(
        {"created_at": created_at.isoformat(), "id": str(item_id)},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        return datetime.fromisoformat(payload["created_at"]), UUID(payload["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise AppError(
            type="invalid_cursor",
            title="Invalid cursor",
            status=422,
            detail="The pagination cursor is invalid or expired.",
        ) from exc
