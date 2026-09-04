from enum import StrEnum


class GenerationType(StrEnum):
    FLOOR_PLAN = "floor_plan"
    FACADE = "facade"
    MASTER_PLAN = "master_plan"
    INTERIOR = "interior"


class GenerationStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
