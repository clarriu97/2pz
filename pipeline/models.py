"""Pydantic models for every record that crosses a boundary.

Why models rather than dicts or dataclasses: these shapes are a *contract*.
The Python pipeline writes them, the React app reads them, and the chat
endpoint's tools query them. Validating at the point of construction means a
typo in a field name fails inside the pipeline, where the traceback points at
the cause, rather than surfacing as `undefined` in a map layer or as a
confidently wrong answer from the analyst.

The invariant that matters most is on `AxisScore`: the signed contributions
must sum to the score. The whole explainability claim rests on it, so it is
enforced by a validator rather than trusted.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

# --------------------------------------------------------------------------
# Shared types
# --------------------------------------------------------------------------
BranchLabel = Literal["PROTECT", "HOLD", "SHRINK"]
ZoneLabel = Literal["GROW", "WATCH", "SKIP"]
ProvenanceTier = Literal["real", "derived", "synthetic"]
UrbanContext = Literal["dense_urban", "suburban", "low_density"]
GeocodePrecision = Literal["address", "area", "emirate", "manual"]
Direction = Literal["up", "down", "neutral"]
ConfidenceLevel = Literal["high", "medium", "low"]

Unit = Annotated[float, Field(ge=0.0, le=1.0)]
"""A value already normalised into [0, 1]."""

Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]


class Model(BaseModel):
    """Base for every record. Strict about unknown fields on purpose.

    `extra="forbid"` turns a renamed field into an immediate error instead of a
    silently dropped one, which is the failure mode that would otherwise reach
    the UI as a blank panel.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# --------------------------------------------------------------------------
# Explainability primitives
# --------------------------------------------------------------------------
class Contribution(Model):
    """One signal's signed push on a score."""

    signal: str
    label: str = Field(description="Human-readable name, rendered in the UI")
    raw_value: float | str
    raw_display: str = Field(description="Pre-formatted value with its unit")
    normalised: float
    weight: float
    contribution: float
    direction: Direction
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def _direction_matches_sign(self) -> Contribution:
        expected: Direction = (
            "neutral"
            if abs(self.contribution) < 1e-9
            else ("up" if self.contribution > 0 else "down")
        )
        if self.direction != expected:
            raise ValueError(
                f"direction {self.direction!r} contradicts contribution "
                f"{self.contribution} on signal {self.signal!r}"
            )
        return self


class AxisScore(Model):
    """A score together with the complete breakdown that produced it."""

    axis: str
    score: float
    contributions: list[Contribution] = Field(min_length=1)

    @model_validator(mode="after")
    def _contributions_sum_to_score(self) -> AxisScore:
        """The explainability guarantee, enforced rather than assumed.

        Every claim the UI makes about "why" depends on the breakdown being
        complete. Rounding is applied to individual contributions for display,
        so the tolerance accommodates that, but nothing larger.
        """
        total = sum(c.contribution for c in self.contributions)
        if abs(total - self.score) > 1e-3:
            raise ValueError(
                f"axis {self.axis!r}: contributions sum to {total:.6f} but score is "
                f"{self.score:.6f} — the breakdown would not explain the score"
            )
        return self

    def by_impact(self) -> list[Contribution]:
        """Contributions ordered by absolute magnitude: the biggest driver first."""
        return sorted(self.contributions, key=lambda c: -abs(c.contribution))


class AnalystNote(Model):
    """An LLM-written note, with enough metadata to distrust it when stale."""

    text: str = Field(min_length=1)
    model: str
    stale: bool = Field(
        description="True when the payload the note was generated from has since changed"
    )


class Confidence(Model):
    level: ConfidenceLevel
    caveats: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Sourced records
# --------------------------------------------------------------------------
class Branch(Model):
    """A physical lounge, as sourced. No scores yet."""

    branch_id: str = Field(pattern=r"^BD\d{2}$")
    name: str
    area: str
    emirate: str
    address: str
    lat: Latitude
    lon: Longitude
    rating: float = Field(ge=0, le=5)
    review_count: int = Field(ge=0)
    urban_context: UrbanContext
    catchment_radius_m: int = Field(gt=0)
    # Synthetic operational fields, declared as such in config.PROVENANCE.
    momentum: Unit = 0.0
    chair_utilisation: Unit = 0.0
    geocode_precision: GeocodePrecision = "address"
    flags: list[str] = Field(default_factory=list)


class Competitor(Model):
    """A competing venue from OpenStreetMap. Location real, rating simulated."""

    competitor_id: str
    name: str
    lat: Latitude
    lon: Longitude
    category: Literal["beauty_salon", "hairdresser", "massage", "spa", "other"]
    tier: Literal["premium", "mid", "value"]
    rating: float = Field(ge=0, le=5, description="SIMULATED — OSM carries no ratings")
    nearest_branch_id: str
    distance_to_nearest_m: int = Field(ge=0)


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------
Ring = list[list[float]]
"""A closed GeoJSON linear ring of [lon, lat] pairs."""


def validate_ring(ring: Ring, what: str) -> Ring:
    """A GeoJSON linear ring must repeat its first vertex to close.

    Some renderers tolerate an open ring and others silently drop the polygon,
    so an unclosed ring is rejected at construction rather than discovered as
    a missing map layer.
    """
    if len(ring) < 4:
        raise ValueError(f"{what} needs at least 4 positions, got {len(ring)}")
    if ring[0] != ring[-1]:
        raise ValueError(f"{what} is not closed: {ring[0]} != {ring[-1]}")
    return ring


class Catchment(Model):
    branch_id: str
    radius_m: int = Field(gt=0)
    area_km2: float = Field(gt=0)
    ring: Ring

    @model_validator(mode="after")
    def _ring_is_closed(self) -> Catchment:
        validate_ring(self.ring, f"catchment ring for {self.branch_id}")
        return self


class OverlapPair(Model):
    """Shared ground between two of our own catchments.

    The two shares are asymmetric by design: a small branch swallowed by a big
    one is the interesting case, and averaging them would hide it.
    """

    branch_a: str
    branch_b: str
    centroid_distance_m: int = Field(ge=0)
    overlap_area_km2: float = Field(ge=0)
    share_of_a: Unit
    share_of_b: Unit


class Sibling(Model):
    branch_id: str
    name: str
    distance_m: int = Field(ge=0)
    share_of_my_catchment: Unit


class Cannibalisation(Model):
    overlapped_share: Unit = Field(
        description="Union (not sum) of sibling overlaps as a share of my catchment"
    )
    sibling_count: int = Field(ge=0)
    siblings: list[Sibling] = Field(default_factory=list)

    @model_validator(mode="after")
    def _count_matches_list(self) -> Cannibalisation:
        if self.sibling_count != len(self.siblings):
            raise ValueError(
                f"sibling_count {self.sibling_count} does not match "
                f"{len(self.siblings)} siblings listed"
            )
        return self


class TopCompetitor(Model):
    competitor_id: str
    name: str
    tier: str
    rating: float
    distance_m: int = Field(ge=0)


class CatchmentCompetition(Model):
    """Competitive pressure inside one branch's catchment."""

    branch_id: str
    competitor_count: int = Field(ge=0)
    competitors_per_km2: float = Field(ge=0)
    saturation_norm: Unit = Field(
        description="Density normalised against the portfolio, not an absolute constant"
    )
    competitor_mean_rating: float = Field(ge=0, le=5)
    competitive_position_stars: float
    premium_share: Unit
    nearest_competitor_m: int = Field(
        ge=-1, description="-1 when no competitor falls inside the catchment"
    )
    top_competitors: list[TopCompetitor] = Field(default_factory=list)


class CatchmentDemand(Model):
    """Built-form demand reading for a branch's catchment."""

    demand_norm: Unit
    cells_in_catchment: int = Field(ge=0)
    residential_features: int = Field(ge=0)
    activity_features: int = Field(ge=0)
    affluence_features: int = Field(ge=0)


class ZoneActivity(Model):
    """Per-H3-cell counts of each demand component, as sourced from OSM."""

    region: str
    residential: int = Field(default=0, ge=0)
    activity: int = Field(default=0, ge=0)
    affluence: int = Field(default=0, ge=0)


class Zone(Model):
    """A candidate H3 cell, before scoring."""

    h3_index: str
    metro: str
    lat: Latitude
    lon: Longitude
    boundary: Ring
    area_km2: float = Field(gt=0)
    # Real, from OSM
    residential_count: int = Field(ge=0)
    activity_count: int = Field(ge=0)
    affluence_count: int = Field(ge=0)
    # Derived
    demand_norm: Unit
    coverage_gap_norm: Unit
    saturation_norm: Unit = 0.0
    nearest_branch_id: str
    nearest_branch_distance_m: int = Field(ge=0)
    inside_own_catchment: bool
    flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _boundary_is_closed(self) -> Zone:
        validate_ring(self.boundary, f"zone boundary for {self.h3_index}")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mapped_feature_count(self) -> int:
        """Total OSM features in this cell — zero means "unknown", not "empty"."""
        return self.residential_count + self.activity_count + self.affluence_count


# --------------------------------------------------------------------------
# Scored output records — what the product actually reads
# --------------------------------------------------------------------------
class BranchRecord(Branch):
    """A branch with its recommendation and the full reasoning behind it."""

    recommendation: BranchLabel
    decision_rule: str = Field(description="The exact rule that fired, shown verbatim in the UI")
    strength: AxisScore
    market: AxisScore
    top_drivers: list[str]
    competition: CatchmentCompetition
    cannibalisation: Cannibalisation
    demand: CatchmentDemand
    catchment_area_km2: float = Field(gt=0)
    confidence: Confidence
    analyst_note: AnalystNote | None = None


class ZoneRecord(Model):
    """A candidate zone with its recommendation and reasoning."""

    zone_id: str
    metro: str
    lat: Latitude
    lon: Longitude
    boundary: Ring
    area_km2: float = Field(gt=0)
    residential_count: int = Field(ge=0)
    activity_count: int = Field(ge=0)
    affluence_count: int = Field(ge=0)
    demand_norm: Unit
    coverage_gap_norm: Unit
    saturation_norm: Unit
    nearest_branch_id: str
    nearest_branch_distance_m: int = Field(ge=0)
    inside_own_catchment: bool
    opportunity: AxisScore
    recommendation: ZoneLabel
    decision_rule: str
    flags: list[str] = Field(default_factory=list)
    analyst_note: AnalystNote | None = None

    @model_validator(mode="after")
    def _boundary_is_closed(self) -> ZoneRecord:
        validate_ring(self.boundary, f"zone boundary for {self.zone_id}")
        return self


# --------------------------------------------------------------------------
# Model card
# --------------------------------------------------------------------------
class ProvenanceEntry(Model):
    tier: ProvenanceTier
    source: str


class ModelCardCounts(Model):
    branches: int = Field(ge=0)
    competitors: int = Field(ge=0)
    scored_zones: int = Field(ge=0)
    branch_labels: dict[str, int]
    zone_labels: dict[str, int]


class ModelCard(Model):
    """A machine-readable snapshot of exactly how the committed dataset was made.

    The UI renders this, and the chat endpoint is handed it as context, so the
    parameters a reviewer reads are provably the ones that produced the numbers
    on screen rather than a hand-written description that can drift.
    """

    sources_as_of: str = Field(
        description="Declared in config, not read from the clock: the date the raw caches "
        "were last refreshed. A run timestamp would make the output non-reproducible and "
        "would tell a reviewer nothing they could check."
    )
    dataset_fingerprint: str = Field(
        description="sha256 over the committed raw inputs and the model config — identifies "
        "this dataset version, and changes if any input or weight does."
    )
    seed: int
    counts: ModelCardCounts
    geography: dict[str, object]
    branch_model: dict[str, object]
    zone_model: dict[str, object]
    normalisation: dict[str, object]
    provenance: dict[str, ProvenanceEntry]
