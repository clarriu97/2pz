"""Shared fixtures.

The fixtures build a small synthetic portfolio with hand-chosen geometry, so
the geographic assertions can be reasoned about on paper rather than compared
against whatever the real dataset happens to contain. Tests that need the real
committed data ask for `real_branches` instead.
"""

from __future__ import annotations

import pytest

from pipeline.models import (
    Branch,
    Cannibalisation,
    CatchmentCompetition,
    Competitor,
    Sibling,
    TopCompetitor,
    Zone,
    ZoneActivity,
)


def make_branch(
    branch_id: str = "BD01",
    *,
    lat: float = 25.2,
    lon: float = 55.27,
    rating: float = 4.6,
    review_count: int = 400,
    radius_m: int = 4000,
    momentum: float = 0.5,
    urban_context: str = "suburban",
    geocode_precision: str = "address",
    area: str = "Testville",
) -> Branch:
    return Branch(
        branch_id=branch_id,
        name=f"Bedashing {area}",
        area=area,
        emirate="Dubai",
        address=f"{area}, Dubai",
        lat=lat,
        lon=lon,
        rating=rating,
        review_count=review_count,
        urban_context=urban_context,  # type: ignore[arg-type]
        catchment_radius_m=radius_m,
        momentum=momentum,
        chair_utilisation=0.6,
        geocode_precision=geocode_precision,  # type: ignore[arg-type]
    )


def make_competition(
    branch_id: str = "BD01",
    *,
    count: int = 20,
    per_km2: float = 0.4,
    saturation: float = 0.5,
    mean_rating: float = 4.4,
    position: float = 0.2,
) -> CatchmentCompetition:
    return CatchmentCompetition(
        branch_id=branch_id,
        competitor_count=count,
        competitors_per_km2=per_km2,
        saturation_norm=saturation,
        competitor_mean_rating=mean_rating,
        competitive_position_stars=position,
        premium_share=0.1,
        nearest_competitor_m=300,
        top_competitors=[
            TopCompetitor(
                competitor_id="n1", name="Rival Salon", tier="mid", rating=4.4, distance_m=300
            )
        ],
    )


def make_cannibalisation(share: float = 0.0, siblings: int = 0) -> Cannibalisation:
    sibs = [
        Sibling(
            branch_id=f"BD{i + 2:02d}",
            name=f"Sibling {i}",
            distance_m=2000 + i * 500,
            share_of_my_catchment=round(share / max(siblings, 1), 4),
        )
        for i in range(siblings)
    ]
    return Cannibalisation(overlapped_share=share, sibling_count=len(sibs), siblings=sibs)


def make_zone(
    h3_index: str = "871e1d0ffffffff",
    *,
    demand: float = 0.5,
    gap: float = 0.5,
    saturation: float = 0.2,
    inside: bool = False,
    distance_m: int = 6000,
    residential: int = 40,
    activity: int = 20,
    affluence: int = 5,
) -> Zone:
    return Zone(
        h3_index=h3_index,
        metro="Dubai",
        lat=25.2,
        lon=55.3,
        boundary=[[55.3, 25.2], [55.31, 25.2], [55.31, 25.21], [55.3, 25.21], [55.3, 25.2]],
        area_km2=5.16,
        residential_count=residential,
        activity_count=activity,
        affluence_count=affluence,
        demand_norm=demand,
        coverage_gap_norm=gap,
        saturation_norm=saturation,
        nearest_branch_id="BD01",
        nearest_branch_distance_m=distance_m,
        inside_own_catchment=inside,
    )


@pytest.fixture
def branch() -> Branch:
    return make_branch()


@pytest.fixture
def competition() -> CatchmentCompetition:
    return make_competition()


@pytest.fixture
def zone() -> Zone:
    return make_zone()


@pytest.fixture
def cluster_branches() -> list[Branch]:
    """Three branches: two overlapping heavily, one far away.

    BD01 and BD02 sit 2 km apart with 4 km radii, so their catchments overlap
    substantially. BD03 is 60 km away and must not overlap either. BD02's
    radius is deliberately smaller so the overlap shares are asymmetric.
    """
    return [
        make_branch("BD01", lat=25.20, lon=55.27, radius_m=4000, area="Alpha"),
        make_branch("BD02", lat=25.20, lon=55.29, radius_m=2500, area="Beta"),
        make_branch("BD03", lat=24.70, lon=55.27, radius_m=4000, area="Gamma"),
    ]


@pytest.fixture
def competitors_nearby() -> list[Competitor]:
    """Competitors placed at known distances from BD01 at (25.20, 55.27)."""
    return [
        Competitor(
            competitor_id="n1",
            name="Close Rival",
            lat=25.205,
            lon=55.27,
            category="beauty_salon",
            tier="mid",
            rating=4.3,
            nearest_branch_id="BD01",
            distance_to_nearest_m=556,
        ),
        Competitor(
            competitor_id="n2",
            name="Premium Spa",
            lat=25.21,
            lon=55.27,
            category="spa",
            tier="premium",
            rating=4.8,
            nearest_branch_id="BD01",
            distance_to_nearest_m=1112,
        ),
        Competitor(
            competitor_id="n3",
            name="Far Barber",
            lat=25.60,
            lon=55.27,
            category="hairdresser",
            tier="value",
            rating=4.0,
            nearest_branch_id="BD01",
            distance_to_nearest_m=44_000,
        ),
    ]


@pytest.fixture
def activity_cells() -> dict[str, ZoneActivity]:
    import h3

    from pipeline import config

    # One dense cell on top of BD01, one sparse cell far away.
    dense = h3.latlng_to_cell(25.20, 55.27, config.H3_RESOLUTION)
    sparse = h3.latlng_to_cell(24.70, 55.27, config.H3_RESOLUTION)
    return {
        dense: ZoneActivity(region="Dubai", residential=300, activity=180, affluence=40),
        sparse: ZoneActivity(region="Dubai", residential=2, activity=1, affluence=0),
    }
