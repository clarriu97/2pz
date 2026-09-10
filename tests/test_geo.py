"""Catchment geometry, self-overlap, saturation and the whitespace grid.

The geometry is the part of this product a reviewer should be able to trust
unreservedly, so it is tested against distances and areas that can be checked
by hand rather than against a golden file.
"""

from __future__ import annotations

import math

import h3
import pytest

from pipeline import config
from pipeline.geo.catchments import (
    build_catchments,
    cannibalisation_index,
    compute_overlaps,
    overlap_features,
)
from pipeline.geo.saturation import compute_competition, zone_saturation
from pipeline.geo.whitespace import build_zones, catchment_demand
from pipeline.models import ZoneActivity
from pipeline.util import haversine_m
from tests.conftest import make_branch


class TestBuildCatchments:
    def test_one_catchment_per_branch(self, cluster_branches) -> None:
        c = build_catchments(cluster_branches)
        assert set(c) == {b.branch_id for b in cluster_branches}

    def test_area_matches_pi_r_squared(self, cluster_branches) -> None:
        c = build_catchments(cluster_branches)["BD01"]
        assert c.area_km2 == pytest.approx(math.pi * 4**2, abs=0.01)

    def test_radius_follows_the_urban_context(self) -> None:
        for context, radius in config.CATCHMENT_RADIUS_M.items():
            b = make_branch(urban_context=context, radius_m=radius)
            assert build_catchments([b])["BD01"].radius_m == radius


class TestComputeOverlaps:
    def test_nearby_branches_overlap(self, cluster_branches) -> None:
        pairs = compute_overlaps(cluster_branches)
        assert {(p.branch_a, p.branch_b) for p in pairs} == {("BD01", "BD02")}

    def test_distant_branches_are_rejected_without_geometry(self, cluster_branches) -> None:
        # BD03 is 55 km away; no pair involving it should exist.
        pairs = compute_overlaps(cluster_branches)
        assert all("BD03" not in (p.branch_a, p.branch_b) for p in pairs)

    def test_shares_are_asymmetric_and_the_smaller_branch_loses_more(
        self, cluster_branches
    ) -> None:
        """The asymmetry is the decision-relevant part.

        A small branch swallowed by a big one is the consolidation candidate;
        averaging the two shares would hide exactly that.
        """
        p = compute_overlaps(cluster_branches)[0]
        assert p.branch_a == "BD01"  # 4 km radius
        assert p.branch_b == "BD02"  # 2.5 km radius
        assert p.share_of_b > p.share_of_a

    def test_overlap_area_is_smaller_than_either_catchment(self, cluster_branches) -> None:
        p = compute_overlaps(cluster_branches)[0]
        smaller = math.pi * 2.5**2
        assert 0 < p.overlap_area_km2 < smaller

    def test_identical_locations_overlap_almost_entirely(self) -> None:
        a = make_branch("BD01", lat=25.2, lon=55.27, radius_m=3000)
        b = make_branch("BD02", lat=25.2, lon=55.27, radius_m=3000)
        p = compute_overlaps([a, b])[0]
        assert p.share_of_a == pytest.approx(1.0, abs=0.01)

    def test_touching_catchments_produce_no_meaningful_overlap(self) -> None:
        # Exactly radius_a + radius_b apart: tangent circles.
        m_lat, _ = (111_132.0, 0)
        a = make_branch("BD01", lat=25.0, lon=55.0, radius_m=2000)
        b = make_branch("BD02", lat=25.0 + 4000 / m_lat, lon=55.0, radius_m=2000)
        pairs = compute_overlaps([a, b])
        assert pairs == [] or pairs[0].overlap_area_km2 < 0.01

    def test_distance_is_recorded_in_metres(self, cluster_branches) -> None:
        p = compute_overlaps(cluster_branches)[0]
        expected = haversine_m(25.20, 55.27, 25.20, 55.29)
        assert p.centroid_distance_m == pytest.approx(expected, abs=2)


class TestCannibalisationIndex:
    def test_every_branch_gets_an_entry(self, cluster_branches) -> None:
        index = cannibalisation_index(cluster_branches, compute_overlaps(cluster_branches))
        assert set(index) == {"BD01", "BD02", "BD03"}

    def test_an_isolated_branch_has_no_overlap(self, cluster_branches) -> None:
        index = cannibalisation_index(cluster_branches, compute_overlaps(cluster_branches))
        assert index["BD03"].overlapped_share == 0.0
        assert index["BD03"].sibling_count == 0

    def test_overlapping_branches_record_each_other(self, cluster_branches) -> None:
        index = cannibalisation_index(cluster_branches, compute_overlaps(cluster_branches))
        assert index["BD01"].sibling_count == 1
        assert index["BD01"].siblings[0].branch_id == "BD02"

    def test_the_share_never_exceeds_one_with_many_overlapping_siblings(self) -> None:
        """The union-not-sum guarantee.

        Three siblings stacked on the same spot all cover the same ground.
        Summing their pairwise shares would give ~3.0 and push a healthy
        cluster to a false SHRINK; the union must stay a real share.
        """
        branches = [
            make_branch("BD01", lat=25.2, lon=55.27, radius_m=4000),
            make_branch("BD02", lat=25.2, lon=55.271, radius_m=4000),
            make_branch("BD03", lat=25.2, lon=55.272, radius_m=4000),
            make_branch("BD04", lat=25.2, lon=55.273, radius_m=4000),
        ]
        index = cannibalisation_index(branches, compute_overlaps(branches))
        assert index["BD01"].sibling_count == 3
        assert index["BD01"].overlapped_share <= 1.0
        naive_sum = sum(s.share_of_my_catchment for s in index["BD01"].siblings)
        assert naive_sum > index["BD01"].overlapped_share

    def test_siblings_are_ordered_by_how_much_they_take(self) -> None:
        branches = [
            make_branch("BD01", lat=25.2, lon=55.27, radius_m=4000),
            make_branch("BD02", lat=25.2, lon=55.275, radius_m=4000),  # very close
            make_branch("BD03", lat=25.2, lon=55.33, radius_m=4000),  # further
        ]
        index = cannibalisation_index(branches, compute_overlaps(branches))
        shares = [s.share_of_my_catchment for s in index["BD01"].siblings]
        assert shares == sorted(shares, reverse=True)


class TestOverlapFeatures:
    def test_produces_a_closed_polygon_per_pair(self, cluster_branches) -> None:
        features = overlap_features(cluster_branches, compute_overlaps(cluster_branches))
        assert len(features) == 1
        ring = features[0]["geometry"]["coordinates"][0]
        assert ring[0] == ring[-1]
        assert len(ring) > 10

    def test_properties_name_both_branches(self, cluster_branches) -> None:
        props = overlap_features(cluster_branches, compute_overlaps(cluster_branches))[0][
            "properties"
        ]
        assert props["branch_a"] == "BD01"
        assert props["branch_b"] == "BD02"
        assert props["pair_id"] == "BD01~BD02"

    def test_features_are_ordered_largest_overlap_first(self) -> None:
        branches = [
            make_branch("BD01", lat=25.20, lon=55.270, radius_m=4000),
            make_branch("BD02", lat=25.20, lon=55.275, radius_m=4000),
            make_branch("BD03", lat=25.20, lon=55.330, radius_m=4000),
        ]
        features = overlap_features(branches, compute_overlaps(branches))
        areas = [f["properties"]["overlap_area_km2"] for f in features]
        assert areas == sorted(areas, reverse=True)

    def test_the_polygon_sits_between_the_two_branches(self, cluster_branches) -> None:
        ring = overlap_features(cluster_branches, compute_overlaps(cluster_branches))[0][
            "geometry"
        ]["coordinates"][0]
        lons = [p[0] for p in ring]
        # The lens between branches at 55.27 and 55.29 must lie in that band.
        assert 55.25 < sum(lons) / len(lons) < 55.31


class TestCompetition:
    def test_only_competitors_inside_the_catchment_are_counted(
        self, cluster_branches, competitors_nearby
    ) -> None:
        catchments = build_catchments(cluster_branches)
        comp = compute_competition(cluster_branches, competitors_nearby, catchments)
        # Two rivals are within 4 km of BD01; the third is 44 km away.
        assert comp["BD01"].competitor_count == 2

    def test_competitive_position_is_our_rating_minus_the_local_mean(
        self, cluster_branches, competitors_nearby
    ) -> None:
        catchments = build_catchments(cluster_branches)
        comp = compute_competition(cluster_branches, competitors_nearby, catchments)["BD01"]
        assert comp.competitor_mean_rating == pytest.approx((4.3 + 4.8) / 2, abs=1e-3)
        assert comp.competitive_position_stars == pytest.approx(4.6 - 4.55, abs=1e-3)

    def test_position_is_zero_when_no_rival_is_in_range(self, cluster_branches) -> None:
        catchments = build_catchments(cluster_branches)
        comp = compute_competition(cluster_branches, [], catchments)["BD01"]
        assert comp.competitor_count == 0
        assert comp.competitive_position_stars == 0.0
        assert comp.nearest_competitor_m == -1

    def test_density_is_per_square_kilometre(self, cluster_branches, competitors_nearby) -> None:
        catchments = build_catchments(cluster_branches)
        comp = compute_competition(cluster_branches, competitors_nearby, catchments)["BD01"]
        assert comp.competitors_per_km2 == pytest.approx(2 / catchments["BD01"].area_km2, abs=1e-3)

    def test_saturation_is_normalised_across_the_portfolio(self, competitors_nearby) -> None:
        """Saturation must mean "crowded relative to where else we trade".

        An absolute constant would make every UAE catchment look identical.
        """
        branches = [
            make_branch("BD01", lat=25.205, lon=55.27, radius_m=4000),  # rivals nearby
            make_branch("BD02", lat=24.00, lon=54.00, radius_m=4000),  # empty
        ]
        catchments = build_catchments(branches)
        comp = compute_competition(branches, competitors_nearby, catchments)
        assert comp["BD01"].saturation_norm > comp["BD02"].saturation_norm
        assert comp["BD02"].saturation_norm == 0.0

    def test_top_competitors_are_the_nearest_and_are_capped(self, cluster_branches) -> None:
        from pipeline.models import Competitor

        many = [
            Competitor(
                competitor_id=f"n{i}",
                name=f"Rival {i}",
                lat=25.20 + i * 0.001,
                lon=55.27,
                category="beauty_salon",
                tier="mid",
                rating=4.4,
                nearest_branch_id="BD01",
                distance_to_nearest_m=i * 111,
            )
            for i in range(1, 15)
        ]
        catchments = build_catchments(cluster_branches)
        comp = compute_competition(cluster_branches, many, catchments)["BD01"]
        assert len(comp.top_competitors) == 8
        distances = [c.distance_m for c in comp.top_competitors]
        assert distances == sorted(distances)


class TestZoneSaturation:
    def test_cells_with_competitors_score_above_empty_cells(self, competitors_nearby) -> None:
        cells = {
            h3.latlng_to_cell(c.lat, c.lon, config.H3_RESOLUTION): None for c in competitors_nearby
        }
        empty = h3.latlng_to_cell(24.0, 54.0, config.H3_RESOLUTION)
        cells[empty] = None
        sat = zone_saturation(competitors_nearby, cells, 5.16)  # type: ignore[arg-type]
        assert sat[empty] == 0.0
        assert max(sat.values()) > 0.0

    def test_returns_zero_everywhere_when_there_are_no_competitors(self) -> None:
        cells = {h3.latlng_to_cell(25.2, 55.27, config.H3_RESOLUTION): None}
        assert zone_saturation([], cells, 5.16) == dict.fromkeys(cells, 0.0)  # type: ignore[arg-type]


class TestBuildZones:
    def test_grids_every_configured_metro(self, cluster_branches) -> None:
        zones = build_zones(cluster_branches, {})
        assert {z.metro for z in zones} == set(config.WHITESPACE_BBOXES)

    def test_empty_cells_are_still_produced_and_flagged(self, cluster_branches) -> None:
        # The map must be able to say "unknown" rather than silently omit.
        zones = build_zones(cluster_branches, {})
        assert all("no_osm_features" in z.flags for z in zones)
        assert all(z.demand_norm == 0.0 for z in zones)

    def test_a_cell_on_a_branch_is_inside_its_catchment(self, cluster_branches) -> None:
        zones = build_zones(cluster_branches, {})
        on_top = min(zones, key=lambda z: haversine_m(z.lat, z.lon, 25.20, 55.27))
        assert on_top.inside_own_catchment
        assert on_top.coverage_gap_norm == 0.0
        assert on_top.nearest_branch_id in {"BD01", "BD02"}

    def test_coverage_gap_is_normalised_by_the_branch_radius(self) -> None:
        """3 km from a tight catchment is a gap; from a wide one it is served.

        Normalising by a fixed distance instead would make the signal mean
        "far" rather than "under-served" — the whole point of the measure.
        """
        tight = make_branch("BD01", lat=25.20, lon=55.27, radius_m=2500)
        wide = make_branch("BD01", lat=25.20, lon=55.27, radius_m=6000)

        def gap_at(branch, lat: float, lon: float) -> float:
            zones = build_zones([branch], {})
            cell = min(zones, key=lambda z: haversine_m(z.lat, z.lon, lat, lon))
            return cell.coverage_gap_norm

        # A point ~4 km north of the branch.
        assert gap_at(tight, 25.236, 55.27) > 0.0
        assert gap_at(wide, 25.236, 55.27) == 0.0

    def test_demand_rises_with_mapped_features(self, cluster_branches) -> None:
        dense = h3.latlng_to_cell(25.20, 55.27, config.H3_RESOLUTION)
        activity = {
            dense: ZoneActivity(region="Dubai", residential=350, activity=200, affluence=50)
        }
        zones = {z.h3_index: z for z in build_zones(cluster_branches, activity)}
        assert zones[dense].demand_norm > 0.5
        others = [z.demand_norm for k, z in zones.items() if k != dense]
        assert max(others) == 0.0

    def test_a_retail_only_cell_is_flagged_non_residential(self, cluster_branches) -> None:
        idx = h3.latlng_to_cell(25.20, 55.27, config.H3_RESOLUTION)
        activity = {idx: ZoneActivity(region="Dubai", residential=0, activity=30, affluence=2)}
        zones = {z.h3_index: z for z in build_zones(cluster_branches, activity)}
        assert "non_residential_zone" in zones[idx].flags

    def test_boundaries_are_closed_hexagons(self, cluster_branches) -> None:
        z = build_zones(cluster_branches, {})[0]
        assert len(z.boundary) == 7
        assert z.boundary[0] == z.boundary[-1]


class TestCatchmentDemand:
    def test_averages_rather_than_sums_across_cells(self, activity_cells) -> None:
        """Summing would reward a wide catchment for being wide.

        A low-density branch with a 6 km radius would outscore a dense-urban
        one with 2.5 km on area alone, which inverts the thing we are trying
        to measure: intensity of demand, not extent of coverage.
        """
        tight = make_branch("BD01", lat=25.20, lon=55.27, radius_m=2500)
        wide = make_branch("BD01", lat=25.20, lon=55.27, radius_m=6000)
        assert (
            catchment_demand([tight], activity_cells)["BD01"].demand_norm
            >= catchment_demand([wide], activity_cells)["BD01"].demand_norm
        )

    def test_reports_the_underlying_feature_counts(self, activity_cells) -> None:
        b = make_branch("BD01", lat=25.20, lon=55.27, radius_m=4000)
        d = catchment_demand([b], activity_cells)["BD01"]
        assert d.residential_features == 300
        assert d.activity_features == 180
        assert d.affluence_features == 40
        assert d.cells_in_catchment >= 1

    def test_a_branch_with_no_nearby_cells_reads_zero(self, activity_cells) -> None:
        far = make_branch("BD01", lat=22.0, lon=53.0, radius_m=2500)
        d = catchment_demand([far], activity_cells)["BD01"]
        assert d.cells_in_catchment == 0
        assert d.demand_norm == 0.0

    def test_demand_is_a_valid_share(self, activity_cells) -> None:
        b = make_branch("BD01", lat=25.20, lon=55.27, radius_m=4000)
        assert 0.0 <= catchment_demand([b], activity_cells)["BD01"].demand_norm <= 1.0
