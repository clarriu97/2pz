"""Builders for fully-scored records.

Kept out of conftest.py because these compose the *output* models rather than
the sourced ones, and several tests import them directly.
"""

from __future__ import annotations

from pipeline.models import (
    BranchRecord,
    CatchmentDemand,
    Confidence,
    ZoneRecord,
)
from pipeline.scoring.model import branch_market, branch_strength, zone_opportunity
from tests.conftest import make_branch, make_cannibalisation, make_competition, make_zone


def make_branch_record(
    branch_id: str = "BD01",
    *,
    recommendation: str = "HOLD",
    rule: str = "strength 0.60 and market 0.50 fall between the thresholds",
    overlap: float = 0.0,
    siblings: int = 0,
    caveats: list[str] | None = None,
    demand: float = 0.5,
) -> BranchRecord:
    branch = make_branch(branch_id)
    competition = make_competition(branch_id)
    cannibalisation = make_cannibalisation(overlap, siblings)

    strength = branch_strength(branch, competition)
    market = branch_market(branch, competition, cannibalisation, demand)
    drivers = sorted(
        strength.contributions + market.contributions, key=lambda c: -abs(c.contribution)
    )

    return BranchRecord(
        **branch.model_dump(),
        recommendation=recommendation,  # type: ignore[arg-type]
        decision_rule=rule,
        strength=strength,
        market=market,
        top_drivers=[c.signal for c in drivers[:3]],
        competition=competition,
        cannibalisation=cannibalisation,
        demand=CatchmentDemand(
            demand_norm=demand,
            cells_in_catchment=4,
            residential_features=200,
            activity_features=80,
            affluence_features=12,
        ),
        catchment_area_km2=50.265,
        confidence=Confidence(level="high" if not caveats else "medium", caveats=caveats or []),
    )


def make_zone_record(
    zone_id: str = "871e1d0ffffffff",
    *,
    recommendation: str = "GROW",
    rule: str = "opportunity 0.70 >= 0.62 with a real gap",
    inside: bool = False,
    demand: float = 0.6,
) -> ZoneRecord:
    zone = make_zone(zone_id, demand=demand, inside=inside)
    opportunity = zone_opportunity(zone)
    return ZoneRecord(
        zone_id=zone.h3_index,
        metro=zone.metro,
        lat=zone.lat,
        lon=zone.lon,
        boundary=zone.boundary,
        area_km2=zone.area_km2,
        residential_count=zone.residential_count,
        activity_count=zone.activity_count,
        affluence_count=zone.affluence_count,
        demand_norm=zone.demand_norm,
        coverage_gap_norm=zone.coverage_gap_norm,
        saturation_norm=zone.saturation_norm,
        nearest_branch_id=zone.nearest_branch_id,
        nearest_branch_distance_m=zone.nearest_branch_distance_m,
        inside_own_catchment=zone.inside_own_catchment,
        opportunity=opportunity,
        recommendation=recommendation,  # type: ignore[arg-type]
        decision_rule=rule,
        flags=zone.flags,
    )
