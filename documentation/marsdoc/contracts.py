"""Versioned input and output models. Regenerate wire schemas with marsdoc.schemas."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, HttpUrl, StrictBool, StrictFloat, StringConstraints,
    field_validator, model_validator,
)

def _version_one(value):
    if type(value) is not int or value != 1:
        raise ValueError("schema_version must be the integer 1")
    return value


VersionOne = Annotated[Literal[1], BeforeValidator(_version_one)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)]
Fraction = Annotated[float, Field(ge=0, le=1)]
Position = tuple[StrictFloat, StrictFloat]
FRAME = "IAU_MARS"


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Point(Record):
    type: Literal["Point"]
    coordinates: Position


class Line(Record):
    type: Literal["LineString"]
    coordinates: tuple[Position, ...]


class Polygon(Record):
    type: Literal["Polygon"]
    coordinates: tuple[tuple[Position, ...], ...]


class MultiPolygon(Record):
    type: Literal["MultiPolygon"]
    coordinates: tuple[tuple[tuple[Position, ...], ...], ...]


class Global(Record):
    type: Literal["Global"]


Surface = Annotated[Polygon | MultiPolygon | Global, Field(discriminator="type")]
QueryShape = Annotated[Point | Line | Polygon | MultiPolygon, Field(discriminator="type")]
CatalogueStatus = Literal["complete", "incomplete", "unknown"]
Readiness = Literal["usable", "needs_preprocessing", "unusable", "unknown"]
FootprintStatus = Literal["native_geographic", "canonical_verified", "unavailable", "invalid", "untransformable"]


class MarsCRS(Record):
    body: Literal["Mars"]
    frame: Name
    definition: Name
    latitude_type: Literal["planetocentric", "planetographic"] | None = None
    longitude_direction: Literal["east", "west"] | None = None
    longitude_domain: Literal["signed", "unsigned"] | None = None
    equatorial_radius_m: Positive | None = None
    polar_radius_m: Positive | None = None


class Dataset(Record):
    id: Name
    mission: Name
    instrument: Name
    modality: Name
    product_class: Name
    archive_url: HttpUrl
    version: Name
    catalogue_status: CatalogueStatus


class TimeWindow(Record):
    start: AwareDatetime
    end: AwareDatetime

    @field_validator("start", "end", mode="before")
    @classmethod
    def timestamp(cls, value):
        if not isinstance(value, (str, datetime)) or isinstance(value, str) and "T" not in value:
            raise ValueError("provide an ISO 8601 date and time with an explicit offset")
        return value

    @model_validator(mode="after")
    def ordered(self):
        if self.start > self.end:
            raise ValueError("time interval is reversed")
        return self

    def contains(self, other: "TimeWindow") -> bool:
        return self.start <= other.start <= other.end <= self.end


class Product(Record):
    id: Name
    dataset_id: Name
    version: Name
    source_url: HttpUrl
    source_crs: MarsCRS | None
    processing_level: Name
    readiness: Readiness
    observation_extent_complete: StrictBool = False
    support_extent_complete: StrictBool = False
    variables: tuple[Name, ...] = ()
    native_spacing_m: Positive | None = None
    effective_scale_m: Positive | None = None
    acquisition: TimeWindow | None = None
    compatibility_key: Name | None = None
    provenance: tuple[Name, ...] = Field(min_length=1)
    limitations: tuple[Name, ...] = ()


class Footprint(Record):
    id: Name
    product_id: Name
    source_url: HttpUrl
    status: FootprintStatus
    coverage_kind: Literal["observation", "usable_support"]
    geometry: Surface | None = None
    transform: Name | None = None
    note: Name | None = None


class Inventory(Record):
    id: Name
    modality: Name
    dataset_ids: tuple[Name, ...]
    status: CatalogueStatus
    scope: Surface | None = None
    source_url: HttpUrl
    authority: Name


class Package(Record):
    schema_version: VersionOne
    package_id: Name
    version: Name
    datasets: tuple[Dataset, ...]
    products: tuple[Product, ...]
    footprints: tuple[Footprint, ...]
    inventories: tuple[Inventory, ...] = ()


class ModalityPolicy(Record):
    modality: Name
    axis: Literal["terrain", "science_environment"]
    weight: Positive
    good_spacing_m: Positive | None = None
    poor_spacing_m: Positive | None = None

    @model_validator(mode="after")
    def valid_ramp(self):
        good, poor = self.good_spacing_m, self.poor_spacing_m
        if (good is None) != (poor is None) or (good is not None and poor <= good):
            raise ValueError("set both spacing thresholds with good < poor, or omit both")
        return self


class Tier(Record):
    minimum: Annotated[float, Field(ge=0, le=100)]
    label: Name


class ScoringPolicy(Record):
    version: Name
    boundary_step: Annotated[int, Field(ge=1, le=256, strict=True)]
    tier_tolerance: Annotated[float, Field(ge=0, le=1e-6)]
    modalities: tuple[ModalityPolicy, ...]
    tiers: tuple[Tier, ...]

    @model_validator(mode="after")
    def valid_policy(self):
        axes = {item.axis for item in self.modalities}
        if axes != {"terrain", "science_environment"}:
            raise ValueError("configure at least one modality for each axis")
        if len({item.modality for item in self.modalities}) != len(self.modalities):
            raise ValueError("modality policies must be unique")
        cuts = [item.minimum for item in self.tiers]
        labels = {item.label for item in self.tiers}
        if (not cuts or cuts[0] != 0 or cuts != sorted(set(cuts)) or "Unclassified" in labels
                or len(labels) != len(cuts)
                or any(right - left <= 2 * self.tier_tolerance for left, right in zip(cuts, cuts[1:]))):
            raise ValueError("configure unique, ordered tiers beginning at zero")
        return self


class Requirement(Record):
    variable: Name
    product_classes: tuple[Name, ...] = Field(min_length=1)
    modalities: tuple[Name, ...] = ()
    processing_levels: tuple[Name, ...] = ()
    max_native_spacing_m: Positive | None = None
    max_effective_scale_m: Positive | None = None
    acquisition_window: TimeWindow | None = None


class Calculation(Record):
    id: Name
    requirements: tuple[Requirement, ...] = Field(min_length=1)


class CapabilityQuery(Record):
    schema_version: VersionOne
    geometry: QueryShape
    corridor_width_m: Positive | None = None
    requested: Calculation
    fallbacks: tuple[Calculation, ...] = ()

    @model_validator(mode="after")
    def valid_request(self):
        if self.corridor_width_m is not None and self.geometry.type != "LineString":
            raise ValueError("corridor_width_m requires a LineString")
        ids = [self.requested.id, *(item.id for item in self.fallbacks)]
        if len(set(ids)) != len(ids):
            raise ValueError("calculation IDs must be unique")
        return self


class Cell(Record):
    id: Name
    nside: int
    nested_index: int
    centroid: Position
    area_km2: Positive


class Bounds(Record):
    lower: float
    upper: float


class Issue(Record):
    code: Name
    record_id: Name
    detail: str
    source_url: HttpUrl


class Provenance(Record):
    dataset: Dataset
    product: Product
    footprints: tuple[Footprint, ...]


class ModalityMetric(Record):
    modality: Name
    coverage_state: Literal["verified_coverage", "verified_absence", "unknown"]
    observed_fraction: Fraction
    observed_bounds: Bounds
    usable_fraction: Fraction
    evidence_score: Fraction | None
    evidence_bounds: Bounds
    catalogue_closed: bool
    inventories: tuple[Inventory, ...]
    product_ids: tuple[Name, ...]
    issues: tuple[Issue, ...]


class AxisSummary(Record):
    score: float | None
    bounds: Bounds
    tier: Name
    classification_status: Literal["classified", "unclassified"]
    reason: str | None


class Result(Record):
    schema_version: VersionOne = 1
    package_id: Name
    package_version: Name
    method_version: Name
    limitations: tuple[Name, ...]
    provenance: tuple[Provenance, ...]


class CellSummary(Result):
    policy_version: Name
    policy_sha256: Name
    cell: Cell
    boundary_step: int
    boundary_area_relative_error: float
    terrain: AxisSummary
    science_environment: AxisSummary
    modalities: tuple[ModalityMetric, ...]


class Candidate(Record):
    product_id: Name
    observed_fraction: Fraction
    support_fraction: Fraction
    native_spacing_m: Positive | None
    effective_scale_m: Positive | None
    readiness: Readiness
    reasons: tuple[Name, ...]


class VariableResult(Record):
    variable: Name
    qualified_fraction: Fraction
    covered_by_single_product: bool
    candidates: tuple[Candidate, ...]
    issues: tuple[Issue, ...]
    reason: Name | None


class CalculationResult(Record):
    id: Name
    eligible: bool
    variables: tuple[VariableResult, ...]
    supporting_product_ids: tuple[Name, ...]
    reason: Name | None


class CapabilityResult(Result):
    query: CapabilityQuery
    requested: CalculationResult
    fallbacks: tuple[CalculationResult, ...]
    supported_fallback_ids: tuple[Name, ...]
    measure: Literal["point", "length_m", "area_m2"]
    query_size: Positive
