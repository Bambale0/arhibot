import json
import logging
import sys
from datetime import UTC, datetime

from app.core.config import Settings
from app.core.request_context import get_request_id


class JsonFormatter(logging.Formatter):
    def __init__(self, release_sha: str) -> None:
        super().__init__()
        self.release_sha = release_sha[:64] or "unknown"

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "release_sha": self.release_sha,
        }
        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id
        for key in (
            "method", "path", "status_code", "duration_ms", "error",
            "dependency", "operation", "attempt", "circuit_state",
            "retry_delay_ms", "generation_id", "payment_id",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if settings.is_production:
        handler.setFormatter(JsonFormatter(settings.release_sha))
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
