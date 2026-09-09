from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

QuestionAnswer = str | int | float | bool | list[str]


class QuestionnaireQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str
    kind: Literal["single", "multi", "number", "text", "consent"]
    options: list[str] = Field(default_factory=list)
    required: bool = False
    skip_default: str | list[str] | None = None
    help: str | None = None
    field_hint: str | None = None
    max_selections: int | None = None
    min_value: float | None = None
    max_value: float | None = None
    phase: Literal["pre_render", "review", "application"] = "pre_render"
    condition: dict[str, Any] | None = None
    option_rules: dict[str, dict[str, Any]] = Field(default_factory=dict)
    edit_targets: dict[str, list[str]] = Field(default_factory=dict)


class QuestionnaireDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    title: str
    source_file: str
    order: int
    questions: list[QuestionnaireQuestion]
    scene_policy: dict[str, str] | None = None


class QuestionnaireSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    title: str
    object_keys: list[str]


class QuestionnaireCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    sections: list[QuestionnaireSection]
    questionnaires: list[QuestionnaireDefinition]
    application_key: str
    source_rules: list[str]


class DesignSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catalog_version: str
    selected_objects: list[str] = Field(default_factory=list, max_length=26)
    current_object: str | None = None
    current_question_id: str | None = None
    source_step_completed: bool = False
    source_asset_id: UUID | None = None
    scene_asset_id: UUID | None = None
    answers: dict[str, dict[str, QuestionAnswer]] = Field(default_factory=dict)
    accepted_objects: list[str] = Field(default_factory=list)
    generation_ids: dict[str, UUID] = Field(default_factory=dict)
    edit_question_ids: list[str] = Field(default_factory=list)
    review_comments: dict[str, str] = Field(default_factory=dict)
    application_submitted: bool = False


class DesignSessionResponse(BaseModel):
    session: DesignSession | None = None
