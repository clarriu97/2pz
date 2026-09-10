"""Sourcing: branch loading, competitor derivation, Overpass query construction.

No test here touches the network. The Overpass client is exercised through its
cache and through a stubbed transport, because a test that needs the internet
is a test that fails for reasons unrelated to the code.
"""

from __future__ import annotations

import json

import pytest

from pipeline import config
from pipeline.sourcing import branches as branches_mod
from pipeline.sourcing import competitors as competitors_mod
from pipeline.sourcing import demand as demand_mod
from pipeline.sourcing import osm as osm_mod
from tests.conftest import make_branch

# ---------------------------------------------------------------- branches


class TestAreaContext:
    def test_every_seeded_area_has_a_declared_urban_context(self) -> None:
        """A missing entry silently falls back to `suburban`.

        That would be an invisible assumption about a real branch's catchment,
        so the mapping is asserted to be complete rather than defaulted.
        """
        import csv

        with branches_mod.SEED_CSV.open(encoding="utf-8") as fh:
            areas = {row["area"] for row in csv.DictReader(fh)}
        missing = areas - set(branches_mod.AREA_CONTEXT)
        assert not missing, f"areas without a declared urban context: {sorted(missing)}"

    def test_every_declared_context_is_a_configured_radius(self) -> None:
        for area, context in branches_mod.AREA_CONTEXT.items():
            assert context in config.CATCHMENT_RADIUS_M, f"{area} -> unknown context {context}"


class TestSynthesiseOperational:
    def test_is_deterministic(self) -> None:
        assert branches_mod._synthesise_operational(
            "BD01", 400
        ) == branches_mod._synthesise_operational("BD01", 400)

    def test_differs_between_branches(self) -> None:
        assert branches_mod._synthesise_operational(
            "BD01", 400
        ) != branches_mod._synthesise_operational("BD02", 400)

    def test_values_stay_inside_their_declared_bounds(self) -> None:
        for i in range(1, 60):
            momentum, util = branches_mod._synthesise_operational(f"BD{i:02d}", 100 * i)
            assert 0.0 <= momentum <= 1.0
            assert 0.15 <= util <= 0.98

    def test_momentum_centres_on_flat(self) -> None:
        # 0.5 means "no change versus the branch's own history"; a biased
        # centre would tilt the whole portfolio's strength score.
        values = [branches_mod._synthesise_operational(f"BD{i:02d}", 300)[0] for i in range(1, 40)]
        assert sum(values) / len(values) == pytest.approx(0.5, abs=0.08)


class TestLoadBranches:
    def test_loads_the_committed_dataset(self) -> None:
        loaded = branches_mod.load_branches()
        assert len(loaded) == 23
        assert all(b.branch_id.startswith("BD") for b in loaded)

    def test_all_branches_land_inside_the_uae(self) -> None:
        # A swapped lat/lon or a geocoder resolving to the wrong country is
        # the single most damaging silent failure in this pipeline.
        for b in branches_mod.load_branches():
            assert 22.4 <= b.lat <= 26.2, f"{b.branch_id} latitude {b.lat} is outside the UAE"
            assert 51.0 <= b.lon <= 56.6, f"{b.branch_id} longitude {b.lon} is outside the UAE"

    def test_branch_ids_are_unique(self) -> None:
        ids = [b.branch_id for b in branches_mod.load_branches()]
        assert len(ids) == len(set(ids))

    def test_radius_agrees_with_the_urban_context(self) -> None:
        for b in branches_mod.load_branches():
            assert b.catchment_radius_m == config.CATCHMENT_RADIUS_M[b.urban_context]

    def test_manual_overrides_are_applied_and_marked(self) -> None:
        from pipeline.util import read_json

        overrides = read_json(branches_mod.COORD_OVERRIDES, default={}) or {}
        by_id = {b.branch_id: b for b in branches_mod.load_branches()}
        for bid, override in overrides.items():
            assert by_id[bid].lat == pytest.approx(override["lat"])
            assert by_id[bid].geocode_precision == "manual"


# ---------------------------------------------------------------- competitors


class TestCompetitorClassification:
    @pytest.mark.parametrize(
        ("tags", "expected"),
        [
            ({"leisure": "spa"}, "spa"),
            ({"amenity": "spa"}, "spa"),
            ({"shop": "beauty"}, "beauty_salon"),
            ({"shop": "hairdresser"}, "hairdresser"),
            ({"shop": "massage"}, "massage"),
            ({"shop": "florist"}, "other"),
        ],
    )
    def test_category(self, tags: dict, expected: str) -> None:
        assert competitors_mod._category(tags) == expected

    def test_a_spa_is_always_premium(self) -> None:
        assert competitors_mod._tier("Anywhere", {}, "spa") == "premium"

    def test_premium_wording_promotes_a_salon(self) -> None:
        assert competitors_mod._tier("The Wellness Lounge", {}, "beauty_salon") == "premium"

    def test_a_plain_hairdresser_is_value(self) -> None:
        assert competitors_mod._tier("Ahmed Barber", {}, "hairdresser") == "value"

    def test_a_plain_salon_is_mid(self) -> None:
        assert competitors_mod._tier("Rose Salon", {}, "beauty_salon") == "mid"

    def test_tier_priors_are_ordered_and_realistic_for_the_uae(self) -> None:
        """Calibration guard.

        An earlier, lower prior let Bedashing win its local comparison almost
        everywhere, which saturated `competitive_position` at the clip for 20
        of 23 branches and destroyed the signal. Gulf personal-care ratings
        really do cluster in the mid-4s.
        """
        priors = competitors_mod.TIER_RATING_PRIOR
        assert priors["premium"][0] > priors["mid"][0] > priors["value"][0]
        for mean, sd in priors.values():
            assert 4.2 <= mean <= 4.9
            assert 0.1 <= sd <= 0.5

    def test_every_prior_tier_is_a_tier_the_classifier_can_produce(self) -> None:
        produced = {
            competitors_mod._tier("Spa X", {}, "spa"),
            competitors_mod._tier("Barber", {}, "hairdresser"),
            competitors_mod._tier("Salon", {}, "beauty_salon"),
        }
        assert produced == set(competitors_mod.TIER_RATING_PRIOR)


class TestLoadCompetitors:
    def test_loads_the_committed_dataset(self) -> None:
        comps = competitors_mod.load_competitors(branches_mod.load_branches())
        assert len(comps) > 500

    def test_every_competitor_is_within_the_search_radius_of_a_branch(self) -> None:
        # The bbox fetch is wider than the search radius, so the local trim is
        # what keeps irrelevant venues out of the saturation figures.
        comps = competitors_mod.load_competitors(branches_mod.load_branches())
        assert all(c.distance_to_nearest_m <= config.COMPETITOR_SEARCH_RADIUS_M for c in comps)

    def test_competitor_ids_are_unique(self) -> None:
        comps = competitors_mod.load_competitors(branches_mod.load_branches())
        ids = [c.competitor_id for c in comps]
        assert len(ids) == len(set(ids))

    def test_simulated_ratings_are_plausible(self) -> None:
        comps = competitors_mod.load_competitors(branches_mod.load_branches())
        assert all(3.0 <= c.rating <= 5.0 for c in comps)


# ---------------------------------------------------------------- osm client


class TestBboxQuery:
    def test_expands_each_selector_over_node_and_way(self) -> None:
        q = osm_mod.bbox_query((24.0, 54.0, 25.0, 55.0), ['["shop"="beauty"]'])
        assert 'node["shop"="beauty"](24.0,54.0,25.0,55.0);' in q
        assert 'way["shop"="beauty"](24.0,54.0,25.0,55.0);' in q

    def test_never_asks_for_relations(self) -> None:
        """Relations are why the public instances used to time this out.

        Making Overpass compute geometric centres for relations over a
        metro-sized bbox reliably 504s, while node+way returns the same POIs
        in seconds.
        """
        q = osm_mod.bbox_query((24.0, 54.0, 25.0, 55.0), ['["shop"="beauty"]'])
        assert "rel[" not in q
        assert "nwr" not in q

    def test_requests_tags_and_a_centre(self) -> None:
        q = osm_mod.bbox_query((24.0, 54.0, 25.0, 55.0), ['["shop"="beauty"]'])
        assert q.strip().endswith("out tags center;")


class TestClusterBboxes:
    def test_nearby_branches_share_one_bbox(self) -> None:
        boxes = osm_mod.cluster_bboxes(
            [
                make_branch("BD01", lat=25.20, lon=55.27),
                make_branch("BD02", lat=25.25, lon=55.30),
            ],
            5000,
        )
        assert len(boxes) == 1

    def test_distant_branches_get_separate_bboxes(self) -> None:
        """Grouping by emirate would put Al Ain with Abu Dhabi city.

        They are 130 km apart, so one bbox would cover the empty desert
        between them and inflate the query for nothing.
        """
        boxes = osm_mod.cluster_bboxes(
            [
                make_branch("BD01", lat=24.45, lon=54.38),  # Abu Dhabi city
                make_branch("BD02", lat=24.21, lon=55.74),  # Al Ain
            ],
            5000,
        )
        assert len(boxes) == 2

    def test_the_bbox_contains_its_branches_plus_padding(self) -> None:
        b = make_branch("BD01", lat=25.20, lon=55.27)
        (bbox,) = osm_mod.cluster_bboxes([b], 5000).values()
        south, west, north, east = bbox
        assert south < b.lat < north
        assert west < b.lon < east
        # ~5 km of padding, so at least 0.04 degrees of latitude.
        assert b.lat - south > 0.04

    def test_a_transitive_chain_merges_into_one_cluster(self) -> None:
        # A--B and B--C are each within the link distance, A--C is not.
        boxes = osm_mod.cluster_bboxes(
            [
                make_branch("BD01", lat=25.00, lon=55.00),
                make_branch("BD02", lat=25.25, lon=55.00),
                make_branch("BD03", lat=25.50, lon=55.00),
            ],
            2000,
        )
        assert len(boxes) == 1


class TestOverpassCache:
    def test_a_cached_response_is_served_without_a_request(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(osm_mod, "CACHE_DIR", tmp_path)

        def explode(*_a, **_k):  # pragma: no cover - must never run
            raise AssertionError("the cache should have prevented a network call")

        monkeypatch.setattr(osm_mod.httpx, "post", explode)

        query = "[out:json];node[test];out;"
        path = osm_mod._cache_path(query, "unit")
        path.write_text(json.dumps({"elements": [{"type": "node", "id": 1}]}))

        assert osm_mod.overpass(query, label="unit") == [{"type": "node", "id": 1}]

    def test_the_cache_key_changes_with_the_query(self, tmp_path) -> None:
        # Otherwise editing a selector would silently serve stale data.
        a = osm_mod._cache_path("[out:json];node[a];out;", "unit")
        b = osm_mod._cache_path("[out:json];node[b];out;", "unit")
        assert a != b

    def test_renaming_a_label_does_not_invalidate_the_cache(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The cache tracks the query, not the cluster's display name.

        Refilling it costs an hour of politely rate-limited requests, so a
        cosmetic rename must not throw it away.
        """
        monkeypatch.setattr(osm_mod, "CACHE_DIR", tmp_path)

        def explode(*_a, **_k):  # pragma: no cover - must never run
            raise AssertionError("a rename should not have triggered a request")

        monkeypatch.setattr(osm_mod.httpx, "post", explode)

        query = "[out:json];node[test];out;"
        osm_mod._cache_path(query, "old-name").write_text(
            json.dumps({"elements": [{"type": "node", "id": 1}]})
        )
        assert osm_mod.overpass(query, label="brand-new-name") == [{"type": "node", "id": 1}]

    def test_a_failing_endpoint_falls_through_to_the_next(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(osm_mod, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(osm_mod, "MIN_REQUEST_INTERVAL_S", 0.0)
        monkeypatch.setattr(osm_mod.time, "sleep", lambda _s: None)

        calls: list[str] = []

        class Response:
            def raise_for_status(self) -> None:
                return None

            @staticmethod
            def json() -> dict:
                return {"elements": [{"type": "node", "id": 7}]}

        def post(endpoint, **_kwargs):
            calls.append(endpoint)
            if len(calls) == 1:
                raise RuntimeError("504 from the busiest mirror")
            return Response()

        monkeypatch.setattr(osm_mod.httpx, "post", post)
        result = osm_mod.overpass("[out:json];node[x];out;", label="unit")
        assert result == [{"type": "node", "id": 7}]
        assert len(calls) > 1

    def test_raises_once_every_endpoint_is_exhausted(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(osm_mod, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(osm_mod, "MIN_REQUEST_INTERVAL_S", 0.0)
        monkeypatch.setattr(osm_mod.time, "sleep", lambda _s: None)
        monkeypatch.setattr(
            osm_mod.httpx, "post", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("down"))
        )
        with pytest.raises(RuntimeError, match="all Overpass endpoints failed"):
            osm_mod.overpass("[out:json];node[x];out;", label="unit")


class TestElementCoords:
    def test_reads_a_node_directly(self) -> None:
        assert osm_mod.element_coords({"lat": 25.0, "lon": 55.0}) == (25.0, 55.0)

    def test_falls_back_to_a_way_centre(self) -> None:
        assert osm_mod.element_coords({"center": {"lat": 25.0, "lon": 55.0}}) == (25.0, 55.0)

    def test_returns_none_when_there_is_no_geometry(self) -> None:
        assert osm_mod.element_coords({"id": 1}) is None


# ---------------------------------------------------------------- demand


class TestClassify:
    @pytest.mark.parametrize(
        ("tags", "expected"),
        [
            ({"building": "apartments"}, "residential"),
            ({"landuse": "residential"}, "residential"),
            ({"place": "suburb"}, "residential"),
            ({"amenity": "cafe"}, "activity"),
            ({"shop": "supermarket"}, "activity"),
            ({"tourism": "hotel"}, "affluence"),
            ({"shop": "mall"}, "affluence"),
            ({"leisure": "marina"}, "affluence"),
            ({"healthcare": "clinic"}, "affluence"),
            ({"highway": "bus_stop"}, None),
            ({}, None),
        ],
    )
    def test_classification(self, tags: dict, expected: str | None) -> None:
        assert demand_mod.classify(tags) == expected

    def test_affluence_wins_when_a_feature_is_both(self) -> None:
        """A mall is retail and a premium signal.

        Counting it twice would double-weight big-box districts, so the
        classifier assigns exactly one component and affluence takes priority.
        """
        assert demand_mod.classify({"shop": "mall", "building": "retail"}) == "affluence"

    def test_a_residential_building_that_is_also_a_hotel_reads_as_affluence(self) -> None:
        assert demand_mod.classify({"building": "apartments", "tourism": "hotel"}) == "affluence"

    def test_component_weights_sum_to_one(self) -> None:
        assert sum(demand_mod.COMPONENT_WEIGHTS.values()) == pytest.approx(1.0)

    def test_every_selector_tag_is_classifiable(self) -> None:
        """A fetched tag that no component claims is wasted request budget.

        This asserts the selector list and the classifier cannot drift apart.
        """
        import re

        for selector in demand_mod.SELECTORS:
            key, value = re.match(r'\["([^"]+)"[=~]"?\^?\(?([^")$]+)', selector).groups()
            for v in value.split("|"):
                assert demand_mod.classify({key: v}) is not None, f"{key}={v} unclassified"


class TestMergeBboxes:
    def test_overlapping_boxes_become_one(self) -> None:
        merged = demand_mod.merge_bboxes(
            {
                "a": (24.0, 54.0, 25.0, 55.0),
                "b": (24.5, 54.5, 25.5, 55.5),
            }
        )
        assert len(merged) == 1
        assert next(iter(merged.values())) == (24.0, 54.0, 25.5, 55.5)

    def test_disjoint_boxes_stay_separate(self) -> None:
        merged = demand_mod.merge_bboxes(
            {"a": (24.0, 54.0, 24.5, 54.5), "b": (25.0, 55.0, 25.5, 55.5)}
        )
        assert len(merged) == 2

    def test_names_are_combined_so_logs_stay_readable(self) -> None:
        merged = demand_mod.merge_bboxes(
            {"Dubai": (24.0, 54.0, 25.0, 55.0), "Sharjah": (24.5, 54.5, 25.5, 55.5)}
        )
        assert next(iter(merged)) == "Dubai+Sharjah"

    def test_a_merge_that_creates_a_new_overlap_settles(self) -> None:
        """The second pass exists for exactly this case.

        A and C do not overlap, but both overlap B; after merging A into B the
        result overlaps C, so a single pass would leave two boxes covering the
        same ground.
        """
        merged = demand_mod.merge_bboxes(
            {
                "a": (24.0, 54.0, 24.4, 54.4),
                "c": (24.6, 54.6, 25.0, 55.0),
                "b": (24.3, 54.3, 24.7, 54.7),
            }
        )
        assert len(merged) == 1

    def test_the_real_configuration_collapses_the_duplicated_metros(self) -> None:
        bboxes = dict(config.WHITESPACE_BBOXES)
        bboxes.update(
            osm_mod.cluster_bboxes(branches_mod.load_branches(), config.COMPETITOR_SEARCH_RADIUS_M)
        )
        merged = demand_mod.merge_bboxes(bboxes)
        assert len(merged) < len(bboxes)
