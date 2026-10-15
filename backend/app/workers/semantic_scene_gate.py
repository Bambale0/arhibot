"""Durable one-shot semantic image gate for an initial architecture concept.

The generated candidate is checkpointed before a paid Qwen chat POST.
An ambiguous Qwen submission is never resent, even after worker recovery.
"""
from __future__ import annotations

import asyncio
from hashlib import sha256
from json import JSONDecodeError, JSONDecoder
from uuid import UUID, NAMESPACE_URL, uuid5

from app.core.config import Settings
from app.db.session import get_session_factory
from app.domain.generations.enums import GenerationStatus
from app.providers.neironych_scene_qa import QwenSceneProvider, validate_scene_verdict
from app.providers.nexus import NexusOutcomeUnknown
from app.repositories.generations import GenerationRepository
from app.services.asset_service import LocalMediaStorage

SCENE_QA_KEY = "image_scene_review"
SCENE_QA_VERSION = "architectural-image-qa.v1"
SUPPORTED_JUDGE = "qwen3.8-max"


class SemanticSceneRejected(RuntimeError):
    def __init__(self, report: dict) -> None:
        self.report = report
        super().__init__(
            "Не удалось подтвердить наличие всех выбранных объектов на изображении. "
            "Результат отклонён, кредиты возвращены. Попробуйте другой вариант."
        )


def selected_scene_objects(prompt: str) -> list[dict]:
    """Read required scene objects from the server-authored canonical prompt."""
    if not prompt.startswith("AUROOM_INITIAL_CONCEPT_V1\n") or "STRUCTURED_SPEC:\n" not in prompt:
        return []
    raw = prompt.split("STRUCTURED_SPEC:\n", 1)[1]
    try:
        spec, _ = JSONDecoder().raw_decode(raw)
    except (JSONDecodeError, TypeError) as exc:
        raise ValueError("Initial concept spec cannot be parsed for semantic verification") from exc
    if not isinstance(spec, dict) or spec.get("schema") != "auroom.initial_concept.v1":
        raise ValueError("Initial concept verification requires a canonical scene spec")
    objects = spec.get("task", {}).get("objects")
    if not isinstance(objects, list) or not 1 <= len(objects) <= 40:
        raise ValueError("Initial concept selected-object list is invalid")
    requirements = []
    for item in objects:
        if not isinstance(item, dict):
            raise ValueError("Invalid selected scene object")
        key = item.get("object_key")
        name = item.get("object_name")
        if not isinstance(key, str) or not key or not isinstance(name, str) or not name:
            raise ValueError("Invalid selected scene object identity")
        constraints = item.get("questionnaire_constraints") or []
        if not isinstance(constraints, list):
            raise ValueError("Invalid selected scene constraints")
        # The judge receives only visual requirements, never entire user context,
        # site-photo URLs, original chat history or customer metadata.
        requirements.append({
            "object_key": key,
            "object_name": name,
            "questionnaire_constraints": [
                {"question": str(x.get("question", ""))[:180],
                 "answer": str(x.get("answer", ""))[:250]}
                for x in constraints[:24] if isinstance(x, dict)
            ],
        })
    if len({i["object_key"] for i in requirements}) != len(requirements):
        raise ValueError("Duplicate selected scene objects")
    return requirements


async def read_candidate(snapshot: dict, settings: Settings) -> bytes:
    """Verify immutable candidate bytes across a worker restart."""
    path = snapshot.get("candidate_path")
    digest = snapshot.get("candidate_sha256")
    if not isinstance(path, str) or not path.startswith("internal/semantic-scene/"):
        raise ValueError("Missing frozen semantic candidate path")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("Missing frozen semantic candidate digest")
    data = await asyncio.to_thread(LocalMediaStorage(settings).absolute_path(path).read_bytes)
    if sha256(data).hexdigest() != digest:
        raise ValueError("Semantic candidate was changed after the image task completed")
    return data


async def checkpoint_candidate(
    generation_id: UUID, image_data: bytes, *,
    image_model: str, provider_task_id: str | None,
    fallback_used: bool, extension: str, settings: Settings,
) -> None:
    """Save bytes first, then atomically publish their location to PostgreSQL."""
    digest = sha256(image_data).hexdigest()
    if extension not in {"png", "jpg", "webp"}:
        raise ValueError("Unsupported candidate image extension")
    relative_path = f"internal/semantic-scene/{generation_id}/candidate.{extension}"
    storage = LocalMediaStorage(settings)

    async with get_session_factory()() as db:
        row = await GenerationRepository(db).get_for_update(generation_id)
        if row is None or row.status != GenerationStatus.PROCESSING:
            raise NexusOutcomeUnknown("Semantic candidate job is no longer active")
        report = dict(row.quality_report or {})
        existing = dict(report.get(SCENE_QA_KEY) or {})
        if existing.get("state") not in {"configured", "candidate_ready"}:
            raise NexusOutcomeUnknown("Semantic candidate was already submitted for review")
        if existing.get("candidate_path"):
            if existing.get("candidate_sha256") != digest:
                raise NexusOutcomeUnknown("Saved semantic candidate differs; do not buy another image")
            return
        if existing.get("model") != SUPPORTED_JUDGE:
            raise ValueError("Unexpected frozen semantic QA model")
        await storage.write(relative_path, image_data)
        report[SCENE_QA_KEY] = {
            **existing,
            "state": "candidate_ready",
            "candidate_path": relative_path,
            "candidate_sha256": digest,
            "image_model": image_model,
            "provider_task_id": provider_task_id,
            "fallback_used": bool(fallback_used),
        }
        row.quality_report = report
        await db.commit()


async def evaluate_candidate(
    generation_id: UUID, image_data: bytes, canonical_prompt: str, settings: Settings,
) -> dict:
    """One chargeable Qwen POST at most; results or ambiguous intent are durable."""
    selected = selected_scene_objects(canonical_prompt)
    if not selected:
        raise ValueError("No initial concept objects to review")
    digest = sha256(image_data).hexdigest()
    async with get_session_factory()() as db:
        row = await GenerationRepository(db).get_for_update(generation_id)
        if row is None or row.status != GenerationStatus.PROCESSING:
            raise NexusOutcomeUnknown("Semantic quality job is no longer processing")
        checkpoint = dict((row.quality_report or {}).get(SCENE_QA_KEY) or {})
        if (
            checkpoint.get("model") != SUPPORTED_JUDGE
            or checkpoint.get("candidate_sha256") != digest
        ):
            raise NexusOutcomeUnknown("Semantic review candidate/model checkpoint mismatch")
        state = checkpoint.get("state")
        if state == "reviewed":
            result = checkpoint.get("verdict")
            if not isinstance(result, dict):
                raise NexusOutcomeUnknown("Saved semantic scene verdict is missing")
            if result.get("passed") is not True:
                raise SemanticSceneRejected(checkpoint)
            return result
        if state == "submitted":
            raise NexusOutcomeUnknown(
                "Qwen scene review was already submitted; manual provider reconciliation required",
                request_id=checkpoint.get("request_id"),
            )
        if state != "candidate_ready":
            raise NexusOutcomeUnknown("Unexpected semantic scene audit state")

        key = f"auroom-{generation_id}-semantic-scene-v1"
        checkpoint = {
            **checkpoint,
            "state": "submitted",
            "request_key": key,
            "client_request_id": str(uuid5(NAMESPACE_URL, f"auroom:semantic-scene:{generation_id}")),
            "required_object_keys": [o["object_key"] for o in selected],
        }
        row.quality_report = {**(row.quality_report or {}), SCENE_QA_KEY: checkpoint}
        await db.commit()

    # Synchronous chat endpoint: no documented safe POST replay even if
    # Idempotency-Key was supplied. A timeout means outcome unknown.
    provider = QwenSceneProvider(settings)
    review, request_id = await provider.review_scene(
        model=SUPPORTED_JUDGE,
        image_data=image_data,
        selected_objects=selected,
        idempotency_key=checkpoint["request_key"],
        client_request_id=checkpoint["client_request_id"],
    )
    try:
        verdict = validate_scene_verdict(
            review, checkpoint["required_object_keys"],
        )
    except ValueError as exc:
        raise NexusOutcomeUnknown(
            "Qwen returned an incomplete paid verdict; do not re-submit"
        ) from exc

    try:
        async with get_session_factory()() as db:
            row = await GenerationRepository(db).get_for_update(generation_id)
            if row is None or row.status != GenerationStatus.PROCESSING:
                raise NexusOutcomeUnknown("Semantic review completed after job stopped")
            stored = dict((row.quality_report or {}).get(SCENE_QA_KEY) or {})
            if stored.get("state") != "submitted" or stored.get("request_key") != checkpoint["request_key"]:
                raise NexusOutcomeUnknown("Semantic review state changed before verdict commit")
            stored.update(state="reviewed", verdict=verdict, request_id=request_id)
            row.quality_report = {**(row.quality_report or {}), SCENE_QA_KEY: stored}
            await db.commit()
    except NexusOutcomeUnknown:
        raise
    except Exception as exc:
        raise NexusOutcomeUnknown(
            "Could not persist paid Qwen scene review; never issue a second POST"
        ) from exc

    if not verdict["passed"]:
        raise SemanticSceneRejected(stored)
    return verdict
