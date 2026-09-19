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


class GenerationOrigin(StrEnum):
    GENERIC = "generic"
    LEGACY_INTERNAL = "legacy_internal"
    QUESTIONNAIRE = "questionnaire"
    QUESTIONNAIRE_INITIAL = "questionnaire_initial"
    ADMIN_SANDBOX = "admin_sandbox"
    ADMIN_ORBIT = "admin_orbit"
    ADMIN_FLYOVER = "admin_flyover"
