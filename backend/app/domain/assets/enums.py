from enum import StrEnum


class AssetType(StrEnum):
    IMAGE = "image"


class AssetUploadPurpose(StrEnum):
    GENERATION_INPUT = "generation_input"
    PROJECT_REFERENCE = "project_reference"


class AssetPurpose(StrEnum):
    GENERATION_INPUT = "generation_input"
    PROJECT_REFERENCE = "project_reference"
    GENERATION_OUTPUT = "generation_output"
