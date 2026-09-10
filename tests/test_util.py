"""Geodesy, normalisation and seeded randomness."""

from __future__ import annotations

import math

import pytest

from pipeline import config
from pipeline.util import (
    circle_polygon,
    clamp01,
    haversine_m,
    local_metres_per_degree,
    log_minmax,
    minmax,
    percentile,
    percentile_rank,
    read_json,
    seeded_normal,
    seeded_unit,
    write_json,
)


class TestHaversine:
    def test_zero_distance_to_self(self) -> None:
        assert haversine_m(25.2, 55.27, 25.2, 55.27) == pytest.approx(0.0)

    def test_dubai_to_abu_dhabi(self) -> None:
        # Known real-world distance, ~123 km. This is the sanity check that
        # catches a swapped lat/lon, which is the classic geospatial bug and
        # would silently corrupt every catchment.
        d = haversine_m(25.2048, 55.2708, 24.4539, 54.3773)
        assert d / 1000 == pytest.approx(123, abs=2)

    def test_is_symmetric(self) -> None:
        a = haversine_m(25.2, 55.27, 24.45, 54.38)
        b = haversine_m(24.45, 54.38, 25.2, 55.27)
        assert a == pytest.approx(b)

    def test_one_degree_of_latitude_is_about_111km(self) -> None:
        assert haversine_m(25.0, 55.0, 26.0, 55.0) / 1000 == pytest.approx(111, abs=1)


class TestLocalMetresPerDegree:
    def test_longitude_degrees_shrink_towards_the_pole(self) -> None:
        _, at_equator = local_metres_per_degree(0.0)
        _, at_uae = local_metres_per_degree(25.0)
        assert at_uae < at_equator

    def test_latitude_degrees_are_roughly_constant(self) -> None:
        lat_0, _ = local_metres_per_degree(0.0)
        lat_25, _ = local_metres_per_degree(25.0)
        assert abs(lat_0 - lat_25) < 1000


class TestCirclePolygon:
    def test_ring_is_closed(self) -> None:
        ring = circle_polygon(25.2, 55.27, 2000)
        assert ring[0] == ring[-1]
        assert len(ring) == config.CATCHMENT_POLYGON_STEPS + 1

    def test_every_vertex_sits_at_the_requested_radius(self) -> None:
        radius = 3000
        ring = circle_polygon(25.2, 55.27, radius)
        for lon, lat in ring:
            # A locally-flat approximation, so allow 1% — far tighter than the
            # uncertainty in the radius assumption itself.
            assert haversine_m(25.2, 55.27, lat, lon) == pytest.approx(radius, rel=0.01)


class TestNormalisation:
    def test_clamp01_bounds_both_ends(self) -> None:
        assert clamp01(-3) == 0.0
        assert clamp01(0.4) == 0.4
        assert clamp01(9) == 1.0

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(4.20, 0.0), (4.95, 1.0), (4.575, 0.5)],
    )
    def test_minmax_maps_the_declared_band_onto_zero_one(
        self, value: float, expected: float
    ) -> None:
        assert minmax(value, config.RATING_FLOOR, config.RATING_CEIL) == pytest.approx(
            expected, abs=1e-3
        )

    def test_minmax_clamps_outside_the_band(self) -> None:
        assert minmax(3.0, 4.2, 4.95) == 0.0
        assert minmax(5.0, 4.2, 4.95) == 1.0

    def test_minmax_is_neutral_on_a_degenerate_band(self) -> None:
        # A zero-width band means "we cannot discriminate", which should read
        # as the middle rather than as a maximum.
        assert minmax(4.0, 4.0, 4.0) == 0.5

    def test_log_minmax_compresses_the_top_of_the_range(self) -> None:
        # The point of the log scale: going 30 -> 100 reviews should matter
        # more than 1400 -> 1500.
        low_step = log_minmax(100, 30, 1500) - log_minmax(30, 30, 1500)
        high_step = log_minmax(1500, 30, 1500) - log_minmax(1430, 30, 1500)
        assert low_step > high_step

    def test_log_minmax_is_monotonic(self) -> None:
        values = [log_minmax(v, 30, 1500) for v in (30, 100, 400, 900, 1500)]
        assert values == sorted(values)

    def test_log_minmax_survives_zero(self) -> None:
        assert log_minmax(0, 30, 1500) == 0.0

    def test_percentile_rank(self) -> None:
        pop = [1.0, 2.0, 3.0, 4.0]
        assert percentile_rank(2.0, pop) == 0.5
        assert percentile_rank(4.0, pop) == 1.0
        assert percentile_rank(0.5, pop) == 0.0

    def test_percentile_rank_is_neutral_on_an_empty_population(self) -> None:
        assert percentile_rank(1.0, []) == 0.5


class TestSeededRandomness:
    """Every synthetic field must be reproducible, or the demo shifts under us."""

    def test_seeded_unit_is_deterministic(self) -> None:
        assert seeded_unit("BD01", "momentum") == seeded_unit("BD01", "momentum")

    def test_seeded_unit_is_in_range(self) -> None:
        for i in range(200):
            assert 0.0 <= seeded_unit("BD", i) < 1.0

    def test_different_keys_give_different_values(self) -> None:
        assert seeded_unit("BD01", "momentum") != seeded_unit("BD02", "momentum")
        assert seeded_unit("BD01", "momentum") != seeded_unit("BD01", "utilisation")

    def test_seeded_unit_is_well_spread(self) -> None:
        # A hash-derived uniform should not clump; a mean far from 0.5 would
        # mean every synthetic field is biased in the same direction.
        values = [seeded_unit("branch", i) for i in range(2000)]
        assert sum(values) / len(values) == pytest.approx(0.5, abs=0.03)

    def test_seeded_normal_is_deterministic(self) -> None:
        assert seeded_normal("BD01", "x", mean=0.5, sd=0.1) == seeded_normal(
            "BD01", "x", mean=0.5, sd=0.1
        )

    def test_seeded_normal_has_the_requested_moments(self) -> None:
        vals = [seeded_normal("b", i, mean=0.5, sd=0.2) for i in range(3000)]
        mean = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))
        assert mean == pytest.approx(0.5, abs=0.02)
        assert sd == pytest.approx(0.2, abs=0.02)

    def test_changing_the_global_seed_changes_the_output(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        before = seeded_unit("BD01", "momentum")
        monkeypatch.setattr(config, "RANDOM_SEED", config.RANDOM_SEED + 1)
        assert seeded_unit("BD01", "momentum") != before


class TestJsonIO:
    def test_round_trip(self, tmp_path) -> None:
        path = tmp_path / "nested" / "x.json"
        write_json(path, {"a": [1, 2], "b": "é"})
        assert read_json(path) == {"a": [1, 2], "b": "é"}

    def test_missing_file_returns_the_default(self, tmp_path) -> None:
        assert read_json(tmp_path / "nope.json", default={"fallback": True}) == {"fallback": True}

    def test_compact_mode_is_smaller(self, tmp_path) -> None:
        payload = {"a": list(range(50))}
        pretty = write_json(tmp_path / "p.json", payload)
        compact = write_json(tmp_path / "c.json", payload, compact=True)
        assert compact.stat().st_size < pretty.stat().st_size


class TestPercentile:
    """Guards the bug this function was written to fix.

    Indexing a quantile with `int(q * (n - 1))` floors to 0 on a two-element
    list, which collapsed the saturation normalisation band to zero width and
    turned a real signal into a constant 0.5 for every branch.
    """

    def test_interpolates_between_neighbours(self) -> None:
        assert percentile([0.0, 10.0], 0.9) == pytest.approx(9.0)

    def test_does_not_floor_to_the_minimum_on_a_two_element_list(self) -> None:
        values = [0.0, 0.04]
        assert percentile(values, 0.9) > values[0]

    def test_endpoints(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0]
        assert percentile(values, 0.0) == 1.0
        assert percentile(values, 1.0) == 4.0

    def test_median_of_an_odd_list(self) -> None:
        assert percentile([1.0, 5.0, 9.0], 0.5) == pytest.approx(5.0)

    def test_single_value(self) -> None:
        assert percentile([7.0], 0.9) == 7.0

    def test_empty(self) -> None:
        assert percentile([], 0.5) == 0.0
