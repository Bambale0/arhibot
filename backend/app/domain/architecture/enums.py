from enum import StrEnum


class ArchitectureRenderStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ArchitectureRenderBatchStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ArchitectureCameraProfile(StrEnum):
    HERO_CORNER = "hero_corner"
    REVERSE_CORNER = "reverse_corner"
    ELEVATED = "elevated"
