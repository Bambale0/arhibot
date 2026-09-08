from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.architecture.glb import CanonicalGlbBuilder
from app.architecture.render_selection import RenderCandidate, choose_batch_winner
from app.architecture.schemas import ArchitecturePackage
from app.core.config import Settings
from app.db.models.admin import IdeaTemplate
from app.db.models.architecture_renders import ArchitectureRender
from app.db.models.assets import Asset
from app.db.models.projects import Project
from app.domain.architecture.enums import ArchitectureCameraProfile, ArchitectureRenderStatus
from app.repositories.admin import AdminRepository
from app.services.architecture_render_service import digest_architecture_payload
from app.services.asset_service import LocalMediaStorage

_TERMINAL_STATUSES = {
    ArchitectureRenderStatus.COMPLETED,
    ArchitectureRenderStatus.FAILED,
}


@dataclass(frozen=True, slots=True)
class BatchPublicationResult:
    resolved: bool
    winner_render_id: UUID | None = None
    target_idea_id: UUID | None = None
    published: bool = False
    skip_reason: str | None = None


def _current_project_digest(project: Project) -> str | None:
    raw = (project.context or {}).get("architecture")
    if not isinstance(raw, dict):
        return None
    try:
        package = ArchitecturePackage.model_validate(raw)
    except ValidationError:
        return None
    payload = package.model_dump(mode="json", exclude_none=True)
    return digest_architecture_payload(payload)


def _candidate(render: ArchitectureRender) -> RenderCandidate | None:
    if (
        render.status != ArchitectureRenderStatus.COMPLETED
        or render.output_asset_id is None
        or render.quality_score is None
    ):
        return None
    try:
        camera_profile = ArchitectureCameraProfile(render.camera_profile)
    except ValueError:
        return None
    return RenderCandidate(
        render_id=render.id,
        camera_profile=camera_profile,
        quality_score=float(render.quality_score),
        technically_usable=bool((render.quality_report or {}).get("technically_usable")),
    )


class ArchitectureRenderPublicationService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.storage = LocalMediaStorage(settings)
        self.admin_repository = AdminRepository(session)

    def _audit_skip(self, winner: ArchitectureRender, reason: str) -> None:
        self.admin_repository.add_audit(
            actor_user_id=winner.user_id,
            action="idea.architecture_render_batch.skip",
            entity_type="idea",
            entity_id=str(winner.target_idea_id) if winner.target_idea_id else None,
            details={
                "batch_id": str(winner.batch_id) if winner.batch_id else None,
                "render_id": str(winner.id),
                "project_id": str(winner.project_id),
                "source_digest": winner.source_digest,
                "camera_profile": winner.camera_profile,
                "quality_score": winner.quality_score,
                "reason": reason,
            },
        )

    async def _skip(
        self,
        winner: ArchitectureRender,
        reason: str,
    ) -> BatchPublicationResult:
        self._audit_skip(winner, reason)
        await self.session.commit()
        return BatchPublicationResult(
            resolved=True,
            winner_render_id=winner.id,
            target_idea_id=winner.target_idea_id,
            skip_reason=reason,
        )

    async def _has_newer_target_batch(
        self,
        winner: ArchitectureRender,
        renders: list[ArchitectureRender],
    ) -> bool:
        if winner.target_idea_id is None or winner.batch_id is None:
            return False
        newest_current_created_at = max(render.created_at for render in renders)
        result = await self.session.execute(
            select(ArchitectureRender.id)
            .where(
                ArchitectureRender.target_idea_id == winner.target_idea_id,
                ArchitectureRender.batch_id.is_not(None),
                ArchitectureRender.batch_id != winner.batch_id,
                ArchitectureRender.created_at > newest_current_created_at,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def finalize(self, batch_id: UUID) -> BatchPublicationResult:
        result = await self.session.execute(
            select(ArchitectureRender)
            .where(ArchitectureRender.batch_id == batch_id)
            .order_by(ArchitectureRender.created_at.asc(), ArchitectureRender.id.asc())
            .with_for_update()
        )
        renders = list(result.scalars().all())
        if not renders or any(render.status not in _TERMINAL_STATUSES for render in renders):
            return BatchPublicationResult(resolved=False)

        selected = next((render for render in renders if render.selected_for_batch), None)
        if selected is not None:
            return BatchPublicationResult(
                resolved=True,
                winner_render_id=selected.id,
                target_idea_id=selected.target_idea_id,
            )

        candidates = [candidate for render in renders if (candidate := _candidate(render))]
        winner_candidate = choose_batch_winner(candidates)
        if winner_candidate is None:
            return BatchPublicationResult(resolved=True)

        winner = next(render for render in renders if render.id == winner_candidate.render_id)
        winner.selected_for_batch = True
        if winner.target_idea_id is None:
            await self.session.commit()
            return BatchPublicationResult(
                resolved=True,
                winner_render_id=winner.id,
            )
        if await self._has_newer_target_batch(winner, renders):
            return await self._skip(winner, "newer_batch_exists")

        idea_result = await self.session.execute(
            select(IdeaTemplate)
            .where(IdeaTemplate.id == winner.target_idea_id)
            .with_for_update()
        )
        idea = idea_result.scalar_one_or_none()
        if idea is None:
            return await self._skip(winner, "idea_not_found")
        if idea.architecture_project_id != winner.project_id:
            return await self._skip(winner, "idea_project_changed")

        project = await self.session.get(Project, winner.project_id)
        if project is None or _current_project_digest(project) != winner.source_digest:
            return await self._skip(winner, "architecture_changed_after_enqueue")
        if not winner_candidate.technically_usable:
            return await self._skip(winner, "winner_failed_technical_qa")

        output_asset = await self.session.get(Asset, winner.output_asset_id)
        if (
            output_asset is None
            or output_asset.deleted_at is not None
            or output_asset.user_id != winner.user_id
            or output_asset.project_id != winner.project_id
        ):
            return await self._skip(winner, "winner_asset_unavailable")

        try:
            package = ArchitecturePackage.model_validate(winner.architecture)
        except ValidationError:
            return await self._skip(winner, "immutable_snapshot_invalid")
        glb = CanonicalGlbBuilder().build(package)
        if len(glb.data) > self.settings.max_model_size_bytes:
            return await self._skip(winner, "canonical_glb_too_large")

        model_path = f"ideas/{idea.id}/models/architecture-{batch_id}.glb"
        previous_model_path = idea.model_storage_path
        await self.storage.write(model_path, glb.data)

        idea.image_asset_id = output_asset.id
        idea.architecture_snapshot = winner.architecture
        idea.model_storage_path = model_path
        idea.model_original_filename = f"architecture-{batch_id}.glb"
        idea.model_size_bytes = len(glb.data)
        self.admin_repository.add_audit(
            actor_user_id=winner.user_id,
            action="idea.architecture_render_batch.publish",
            entity_type="idea",
            entity_id=str(idea.id),
            details={
                "batch_id": str(batch_id),
                "render_id": str(winner.id),
                "project_id": str(winner.project_id),
                "source_digest": winner.source_digest,
                "camera_profile": winner.camera_profile,
                "quality_score": winner.quality_score,
                "output_asset_id": str(output_asset.id),
                "model_size_bytes": len(glb.data),
            },
        )

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            target = self.storage.absolute_path(model_path)
            if target.exists():
                await asyncio.to_thread(target.unlink, missing_ok=True)
            raise

        if previous_model_path and previous_model_path != model_path:
            previous = self.storage.absolute_path(previous_model_path)
            if previous.exists():
                await asyncio.to_thread(previous.unlink, missing_ok=True)

        return BatchPublicationResult(
            resolved=True,
            winner_render_id=winner.id,
            target_idea_id=idea.id,
            published=True,
        )
