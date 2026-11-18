"""Read-only triage of stuck generations; never submit provider work or mutate ledger.

Run from backend as: python -m app.workers.reconciliation_triage
Output contains aggregate counts only, never users, job identifiers, prompts or keys.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text

from app.db.models.generations import Generation
from app.db.session import dispose_engine, get_session_factory
from app.domain.generations.enums import GenerationStatus


def classify_pending_reconciliation(
    quality_report: dict | None,
    provider_task_present: bool,
) -> str:
    """Classify a checkpoint for HUMAN triage, never authorize auto-requeue."""
    report = quality_report if isinstance(quality_report, dict) else {}
    if report.get("requires_reconciliation"):
        identity_request = report.get("video_identity_request")
        if (
            isinstance(identity_request, dict)
            and identity_request.get("state") == "submitted"
            and not isinstance(report.get("video_identity_review"), dict)
        ):
            return "operator_required_identity_outcome_unknown"

        video_request = report.get("video_request")
        if isinstance(video_request, dict):
            if (
                video_request.get("state") == "prepared"
                and not video_request.get("request_id")
            ):
                return "operator_required_video_create_outcome_unknown"
            if (
                video_request.get("state") == "accepted"
                and isinstance(video_request.get("request_id"), str)
                and bool(video_request.get("request_id"))
            ):
                return "provider_accepted_check_resume_policy"

        return "operator_required_provider_outcome_unknown"
    if provider_task_present:
        return "provider_task_present_check_worker"
    return "stale_without_reconciliation_check_queue"


async def audit_stale_generations(
    *, min_age_minutes: int = 10, limit: int = 1000
) -> dict[str, object]:
    """Snapshot-only query; force PG transaction READ ONLY before any SELECT."""
    if not 1 <= min_age_minutes <= 60 * 24 * 365:
        raise ValueError("min_age_minutes must be within 1..525600")
    if not 1 <= limit <= 10_000:
        raise ValueError("limit must be within 1..10000")

    cutoff = datetime.now(UTC) - timedelta(minutes=min_age_minutes)
    condition = (
        Generation.status == GenerationStatus.PROCESSING,
        func.coalesce(Generation.started_at, Generation.created_at) < cutoff,
    )
    async with get_session_factory()() as session:
        async with session.begin():
            await session.execute(text("SET TRANSACTION READ ONLY"))
            total = (
                await session.execute(
                    select(func.count()).select_from(Generation).where(*condition)
                )
            ).scalar_one()
            rows = (
                await session.execute(
                    select(
                        Generation.created_at,
                        Generation.started_at,
                        Generation.quality_report,
                        Generation.provider_task_id,
                    )
                    .where(*condition)
                    .order_by(Generation.created_at.asc())
                    .limit(limit)
                )
            ).all()
            counts: Counter[str] = Counter(
                classify_pending_reconciliation(row.quality_report, bool(row.provider_task_id))
                for row in rows
            )
            # Query completion leaves no persistent changes even if callers later
            # modify this module; closing the read-only transaction rolls back.
    return {
        "status": "needs_operator_review" if total else "clear",
        "stale_processing_total": int(total),
        "classified_count": len(rows),
        "truncated": int(total) > len(rows),
        "categories": dict(sorted(counts.items())),
        "minimum_age_minutes": min_age_minutes,
        "mode": "read_only",
    }


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-age-minutes", type=int, default=10)
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    try:
        result = await audit_stale_generations(
            min_age_minutes=args.min_age_minutes, limit=args.limit
        )
        print(json.dumps(result, sort_keys=True))
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
