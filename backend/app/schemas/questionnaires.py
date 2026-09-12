from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.generations import NormalizedRect

QuestionAnswer = str | int | float | bool | list[str]

HOUSE_STYLE_INHERITANCE_OBJECTS = frozenset(
    {
        "gostevoy",
        "banya",
        "garazh",
        "naves",
        "letnyaya-kuhnya",
        "besedka",
        "hozblok",
        "detskiy-domik",
    }
)


class QuestionnaireQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str
    kind: Literal["single", "multi", "number", "text", "consent"]
    options: list[str] = Field(default_factory=list)
    required: bool = False
    skip_default: str | list[str] | None = None
    skip_condition: dict[str, Any] | None = None
    help: str | None = None
    field_hint: str | None = None
    placeholder: str | None = None
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


class QuestionnaireSourceText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str
    text: str


class QuestionnaireCatalogAdminUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catalog: QuestionnaireCatalogResponse
    source_texts: dict[str, QuestionnaireSourceText]


class QuestionnaireCatalogAdminResponse(QuestionnaireCatalogAdminUpdate):
    updated_at: datetime


class QuestionnaireProjectStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selected_objects: list[str] = Field(min_length=1, max_length=26)
    plot_area_sotkas: int = Field(ge=4, le=15)


class QuestionnaireObjectAddRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_key: str = Field(min_length=1, max_length=80)


class QuestionnaireGenerationCostResponse(BaseModel):
    generation_type: Literal["master_plan"] = "master_plan"
    credits: int | None = None
    is_available: bool


class DesignSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID = Field(default_factory=uuid4)
    catalog_version: str
    selected_objects: list[str] = Field(default_factory=list, max_length=26)
    plot_area_sotkas: int | None = Field(default=None, ge=4, le=15)
    initial_concept_mode: bool = False
    survey_completed_objects: list[str] = Field(default_factory=list)
    initial_generation_id: UUID | None = None
    initial_concept_accepted: bool = False
    current_object: str | None = None
    current_question_id: str | None = None
    source_step_completed: bool = False
    source_asset_id: UUID | None = None
    scene_asset_id: UUID | None = None
    scene_generation_id: UUID | None = None
    answers: dict[str, dict[str, QuestionAnswer]] = Field(default_factory=dict)
    accepted_objects: list[str] = Field(default_factory=list)
    removed_objects: list[str] = Field(default_factory=list)
    pending_removal_object: str | None = None
    generation_ids: dict[str, UUID] = Field(default_factory=dict)
    edit_question_ids: list[str] = Field(default_factory=list)
    review_comments: dict[str, str] = Field(default_factory=dict)
    edit_regions: dict[str, NormalizedRect] = Field(default_factory=dict)
    lock_regions: dict[str, NormalizedRect] = Field(default_factory=dict)
    region_mode: Literal["edit", "lock"] | None = None
    region_object: str | None = None
    application_submitted: bool = False

    @model_validator(mode="after")
    def validate_region_step(self) -> DesignSession:
        if (self.region_mode is None) != (self.region_object is None):
            raise ValueError("Region mode and region object must be set together.")
        if self.region_object is not None and self.region_object not in self.selected_objects:
            raise ValueError("Region object must belong to the selected questionnaire objects.")
        if len(self.survey_completed_objects) != len(set(self.survey_completed_objects)):
            raise ValueError("Completed questionnaire objects must be unique.")
        if any(key not in self.selected_objects for key in self.survey_completed_objects):
            raise ValueError("Completed questionnaire objects must be selected.")
        if self.initial_concept_accepted and not self.initial_generation_id:
            raise ValueError("Accepted initial concept must reference its generation.")
        if len(self.removed_objects) != len(set(self.removed_objects)):
            raise ValueError("Removed questionnaire objects must be unique.")
        if any(key not in self.selected_objects for key in self.removed_objects):
            raise ValueError("Removed questionnaire objects must be selected.")
        if set(self.removed_objects) & set(self.accepted_objects):
            raise ValueError("A questionnaire object cannot be accepted and removed at once.")
        if (
            self.pending_removal_object is not None
            and self.pending_removal_object not in self.accepted_objects
        ):
            raise ValueError("Pending removal object must currently be accepted.")
        return self

    @model_validator(mode="after")
    def require_accepted_house_for_inherited_style(self) -> DesignSession:
        house_reference_available = "eskez-doma" in self.accepted_objects or (
            self.initial_concept_mode
            and not self.initial_concept_accepted
            and "eskez-doma" in self.selected_objects
        )
        if house_reference_available:
            return self
        for object_key in HOUSE_STYLE_INHERITANCE_OBJECTS:
            if (
                self.answers.get(object_key, {}).get("1") == "Как у дома"
                and object_key not in self.accepted_objects
                and object_key not in self.removed_objects
            ):
                raise ValueError(
                    "Вариант «Как у дома» доступен только при наличии основного дома."
                )
        return self


class DesignSessionResponse(BaseModel):
    session: DesignSession | None = None


class QuestionnaireBriefAnswer(BaseModel):
    question_id: str
    question: str
    answer: QuestionAnswer


class QuestionnaireBriefObject(BaseModel):
    key: str
    title: str
    accepted: bool
    answers: list[QuestionnaireBriefAnswer] = Field(default_factory=list)


class QuestionnaireApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    session_id: UUID
    project_id: UUID
    user_id: UUID
    catalog_version: str
    selected_objects: list[str]
    accepted_objects: list[str]
    answers: dict[str, dict[str, QuestionAnswer]]
    scene_asset_id: UUID | None
    status: str
    telegram_delivery_status: str
    telegram_notified_at: datetime | None
    created_at: datetime
    project_name: str | None = None
    user_name: str | None = None
    scene_asset_url: str | None = None
    final_generation_id: UUID | None = None
    application_contact: str | None = None
    user_email: str | None = None
    telegram_user_id: str | None = None
    brief: list[QuestionnaireBriefObject] = Field(default_factory=list)


class QuestionnaireApplicationSubmitResponse(BaseModel):
    session: DesignSession
    application: QuestionnaireApplicationResponse
