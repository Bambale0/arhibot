from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Point2D(StrictModel):
    x: float
    y: float


class Polygon2D(StrictModel):
    points: list[Point2D] = Field(min_length=3, max_length=256)

    @model_validator(mode="after")
    def require_three_unique_points(self) -> Polygon2D:
        unique = {(point.x, point.y) for point in self.points}
        if len(unique) < 3:
            raise ValueError("A polygon requires at least three unique points.")
        return self


class RoomKind(StrEnum):
    VEHICLE = "vehicle"
    SLEEPING = "sleeping"
    WET = "wet"
    LIVING = "living"
    SERVICE = "service"
    CIRCULATION = "circulation"


class ExternalObjectType(StrEnum):
    POOL = "pool"
    VERANDA = "veranda"
    TERRACE = "terrace"
    BALCONY = "balcony"
    WINTER_GARDEN = "winter_garden"


class RoofType(StrEnum):
    GABLE = "gable"
    HIP = "hip"
    FLAT = "flat"


class CoordinateSystem(StrictModel):
    unit: Literal["meter"] = "meter"
    origin: Point2D = Field(default_factory=lambda: Point2D(x=0.0, y=0.0))
    x_axis: Literal["east"] = "east"
    y_axis: Literal["north"] = "north"
    z_axis: Literal["up"] = "up"


class RoomGeometry(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    kind: RoomKind
    polygon: Polygon2D
    target_area_sqm: float | None = Field(default=None, gt=0)


class LevelGeometry(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    label: str = Field(min_length=1, max_length=120)
    z: float = Field(ge=-20, le=200)
    height: float = Field(gt=1.5, le=8.0)
    footprint: Polygon2D
    rooms: list[RoomGeometry] = Field(default_factory=list, max_length=100)


class ExternalObjectGeometry(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    label: str = Field(min_length=1, max_length=120)
    type: ExternalObjectType
    polygon: Polygon2D
    z: float = Field(default=0.0, ge=-20, le=200)
    height: float = Field(default=0.15, ge=0.0, le=20.0)
    level_id: str | None = Field(default=None, max_length=80)


class RoofGeometry(StrictModel):
    type: RoofType
    eave_z: float = Field(ge=-20, le=250)
    ridge_z: float = Field(ge=-20, le=250)
    ridge_start: Point2D | None = None
    ridge_end: Point2D | None = None
    overhang_m: float = Field(default=0.4, ge=0, le=3)

    @model_validator(mode="after")
    def validate_roof_heights(self) -> RoofGeometry:
        if self.type != RoofType.FLAT and self.ridge_z <= self.eave_z:
            raise ValueError("Pitched roofs require ridge_z greater than eave_z.")
        if self.type == RoofType.GABLE and (self.ridge_start is None or self.ridge_end is None):
            raise ValueError("Gable roofs require ridge_start and ridge_end.")
        return self


class HouseGeometry(StrictModel):
    coordinate_system: CoordinateSystem = Field(default_factory=CoordinateSystem)
    levels: list[LevelGeometry] = Field(min_length=1, max_length=10)
    external_objects: list[ExternalObjectGeometry] = Field(default_factory=list, max_length=50)
    roof: RoofGeometry | None = None


class HouseProgram(StrictModel):
    living_area_sqm: float | None = Field(default=None, gt=0, le=5000)
    bedrooms: int | None = Field(default=None, ge=0, le=30)
    bathrooms: int | None = Field(default=None, ge=0, le=30)
    storeys: int | None = Field(default=None, ge=1, le=10)
    garage_cars: int | None = Field(default=None, ge=0, le=10)


class HouseAppearance(StrictModel):
    architecture_style: str | None = Field(default=None, max_length=80)
    primary_material: str | None = Field(default=None, max_length=80)
    accent_materials: list[str] = Field(default_factory=list, max_length=12)
    roof_material: str | None = Field(default=None, max_length=80)
    glazing: str | None = Field(default=None, max_length=80)
    lighting: str | None = Field(default=None, max_length=80)


class ArchitecturePackage(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    program: HouseProgram = Field(default_factory=HouseProgram)
    geometry: HouseGeometry
    appearance: HouseAppearance = Field(default_factory=HouseAppearance)


class GeometryValidationIssue(StrictModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    path: str | None = None


class GeometryValidationReport(StrictModel):
    valid: bool
    issues: list[GeometryValidationIssue]
    level_areas_sqm: dict[str, float]
    room_areas_sqm: dict[str, float]
    gross_floor_area_sqm: float


class ArchitectureSaveResponse(StrictModel):
    architecture: ArchitecturePackage
    validation: GeometryValidationReport
