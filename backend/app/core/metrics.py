from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import text

from app.core.redis import redis_client
from app.db.session import get_engine
from app.workers.heartbeat import worker_heartbeat_age

HTTP_REQUESTS = Counter(
    'auroom_http_requests_total',
    'HTTP requests completed by the AuRoom API.',
    ['method', 'route', 'status'],
)
HTTP_DURATION = Histogram(
    'auroom_http_request_duration_seconds',
    'HTTP request latency by route template.',
    ['method', 'route'],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
QUEUE_DEPTH = Gauge(
    'auroom_queue_depth',
    'Current Redis queue depth.',
    ['queue'],
)
WORKER_HEARTBEAT_AGE = Gauge(
    'auroom_worker_heartbeat_age_seconds',
    'Age of the most recent worker heartbeat; -1 means unavailable.',
    ['worker'],
)
GENERATION_STATE = Gauge(
    'auroom_generations_in_state',
    'Current number of generation records by state.',
    ['status'],
)
GENERATION_OLDEST_AGE = Gauge(
    'auroom_generation_oldest_age_seconds',
    'Age of the oldest generation in a non-terminal state; 0 when empty.',
    ['status'],
)
GENERATION_FAILURES_LAST_HOUR = Gauge(
    'auroom_generation_failures_last_hour',
    'Generation failures completed in the last hour.',
)
BUILD_INFO = Gauge(
    'auroom_build_info',
    'AuRoom API build identity.',
    ['release_sha'],
)

def observe_http_request(*, method: str, route: str, status_code: int, duration_seconds: float) -> None:
    safe_method = method.upper()[:12]
    safe_route = route if route.startswith('/') else '__unmatched__'
    HTTP_REQUESTS.labels(method=safe_method, route=safe_route, status=str(status_code)).inc()
    HTTP_DURATION.labels(method=safe_method, route=safe_route).observe(max(0.0, duration_seconds))


async def refresh_runtime_metrics(*, release_sha: str) -> None:
    BUILD_INFO.clear()
    BUILD_INFO.labels(release_sha=release_sha[:64] or 'unknown').set(1)

    queues = {
        'generation': 'auroom:generation_queue',
        'generation_processing': 'auroom:generation_processing',
        'broadcast': 'auroom:broadcast_queue',
    }
    for name, key in queues.items():
        try:
            QUEUE_DEPTH.labels(queue=name).set(await redis_client.llen(key))
        except Exception:
            QUEUE_DEPTH.labels(queue=name).set(-1)

    for worker in ('generation', 'broadcast', 'maintenance'):
        try:
            age = await worker_heartbeat_age(worker)
        except Exception:
            age = None
        WORKER_HEARTBEAT_AGE.labels(worker=worker).set(-1 if age is None else age)

    statuses = ('queued', 'processing', 'completed', 'failed')
    try:
        async with get_engine().connect() as connection:
            result = await connection.execute(
                text('SELECT status::text, count(*) FROM generations GROUP BY status')
            )
            counts = {str(status): int(count) for status, count in result.all()}
            age_result = await connection.execute(
                text(
                    "SELECT status::text, EXTRACT(EPOCH FROM (now() - min(COALESCE(started_at, created_at)))) "
                    "FROM generations WHERE status IN ('queued','processing') GROUP BY status"
                )
            )
            ages = {str(status): max(0.0, float(age or 0.0)) for status, age in age_result.all()}
            failed_result = await connection.execute(
                text(
                    "SELECT count(*) FROM generations "
                    "WHERE status='failed' AND completed_at >= now() - interval '1 hour'"
                )
            )
            failed_last_hour = int(failed_result.scalar_one())
    except Exception:
        counts = {status: -1 for status in statuses}
        ages = {'queued': -1, 'processing': -1}
        failed_last_hour = -1

    for status in statuses:
        GENERATION_STATE.labels(status=status).set(counts.get(status, 0))
    for status in ('queued', 'processing'):
        GENERATION_OLDEST_AGE.labels(status=status).set(ages.get(status, 0.0))
    GENERATION_FAILURES_LAST_HOUR.set(failed_last_hour)


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
