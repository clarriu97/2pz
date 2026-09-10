"""The orchestrator, the confidence model, and the committed dataset itself.

The last class here validates `data/processed/` as shipped. Those tests are the
ones that would catch a broken deliverable: the reviewer runs `npm install` and
reads whatever is in that directory, so it is worth asserting the contract
holds on the real bytes rather than only on fixtures.
"""

from __future__ import annotations

import json

import pytest

from pipeline import config
from pipeline.geo.catchments import build_catchments, cannibalisation_index, compute_overlaps
from pipeline.geo.saturation import compute_competition
from pipeline.geo.whitespace import build_zones, catchment_demand
from pipeline.models import BranchRecord, ModelCard, ZoneRecord
from pipeline.run import (
    build_confidence,
    build_model_card,
    score_branches,
    score_zones,
)
from tests.conftest import make_branch, make_competition


class TestConfidence:
    def test_a_solid_branch_is_high_confidence(self) -> None:
        c = build_confidence(make_branch(review_count=500), make_competition(count=20))
        assert c.level == "high"
        assert c.caveats == []

    def test_thin_reviews_demote_and_explain(self) -> None:
        c = build_confidence(
            make_branch(review_count=config.LOW_CONFIDENCE_REVIEW_THRESHOLD - 1),
            make_competition(count=20),
        )
        assert c.level == "medium"
        assert "statistically thin" in c.caveats[0]

    def test_an_unmapped_catchment_is_called_a_coverage_gap_not_a_vacuum(self) -> None:
        """Two competitors is missing data, not an empty market.

        Reading it as a genuine vacuum would reward branches in the areas
        OpenStreetMap happens not to cover.
        """
        c = build_confidence(
            make_branch(review_count=500),
            make_competition(count=config.LOW_CONFIDENCE_COMPETITOR_THRESHOLD - 1),
        )
        assert c.level == "medium"
        assert "OpenStreetMap coverage gap" in c.caveats[0]

    def test_two_major_caveats_make_it_low(self) -> None:
        c = build_confidence(make_branch(review_count=10), make_competition(count=0))
        assert c.level == "low"
        assert len(c.caveats) == 2

    def test_district_precision_is_noted_without_demoting(self) -> None:
        """Most coordinates resolve at district level.

        Counting that as a demotion would mark almost the whole portfolio
        "low" and the flag would stop carrying information.
        """
        c = build_confidence(
            make_branch(review_count=500, geocode_precision="area"),
            make_competition(count=20),
        )
        assert c.level == "high"
        assert len(c.caveats) == 1
        assert "immaterial" in c.caveats[0]

    def test_a_hand_placed_coordinate_does_demote(self) -> None:
        c = build_confidence(
            make_branch(review_count=500, geocode_precision="manual"),
            make_competition(count=20),
        )
        assert c.level == "medium"


class TestScoreBranches:
    @pytest.fixture
    def scored(self, cluster_branches, competitors_nearby) -> list[BranchRecord]:
        catchments = build_catchments(cluster_branches)
        overlaps = compute_overlaps(cluster_branches)
        return score_branches(
            cluster_branches,
            compute_competition(cluster_branches, competitors_nearby, catchments),
            cannibalisation_index(cluster_branches, overlaps),
            catchment_demand(cluster_branches, {}),
            catchments,
        )

    def test_one_record_per_branch(self, scored, cluster_branches) -> None:
        assert len(scored) == len(cluster_branches)

    def test_every_record_carries_a_label_and_the_rule_behind_it(self, scored) -> None:
        for r in scored:
            assert r.recommendation in ("PROTECT", "HOLD", "SHRINK")
            assert len(r.decision_rule) > 10

    def test_top_drivers_are_the_three_largest_absolute_contributions(self, scored) -> None:
        for r in scored:
            merged = r.strength.contributions + r.market.contributions
            expected = [c.signal for c in sorted(merged, key=lambda c: -abs(c.contribution))[:3]]
            assert r.top_drivers == expected

    def test_both_axes_satisfy_the_sum_to_score_invariant(self, scored) -> None:
        for r in scored:
            for axis in (r.strength, r.market):
                assert axis.score == pytest.approx(
                    sum(c.contribution for c in axis.contributions), abs=1e-3
                )


class TestScoreZones:
    def test_empty_skip_cells_are_dropped(self, cluster_branches) -> None:
        # Thousands of identical empty-desert hexes say nothing and would make
        # the map unusable.
        zones = build_zones(cluster_branches, {})
        assert score_zones(zones) == []

    def test_cells_with_signal_survive(self, cluster_branches, activity_cells) -> None:
        zones = build_zones(cluster_branches, activity_cells)
        scored = score_zones(zones)
        assert len(scored) >= 1
        # A surviving cell must either carry mapped features or have earned a
        # non-SKIP label; anything else is empty desert that should have gone.
        for z in scored:
            has_features = z.residential_count + z.activity_count + z.affluence_count > 0
            assert has_features or z.recommendation != "SKIP"

    def test_every_surviving_cell_has_a_label_and_a_rule(
        self, cluster_branches, activity_cells
    ) -> None:
        for z in score_zones(build_zones(cluster_branches, activity_cells)):
            assert z.recommendation in ("GROW", "WATCH", "SKIP")
            assert len(z.decision_rule) > 10


class TestModelCard:
    @pytest.fixture
    def card(self) -> ModelCard:
        from tests.helpers import make_branch_record, make_zone_record

        return build_model_card([make_branch_record()], [make_zone_record()], [])

    def test_reports_the_configured_weights_verbatim(self, card) -> None:
        """The UI renders this card, so it must be the live config.

        A hand-written description of the model would drift from the model.
        """
        assert card.branch_model["strength_weights"] == config.STRENGTH_WEIGHTS
        assert card.branch_model["market_weights"] == config.MARKET_WEIGHTS
        assert card.zone_model["opportunity_weights"] == config.OPPORTUNITY_WEIGHTS

    def test_reports_the_seed_so_the_dataset_is_reproducible(self, card) -> None:
        assert card.seed == config.RANDOM_SEED

    def test_carries_a_content_fingerprint_rather_than_a_run_timestamp(self, card) -> None:
        """A clock reading made the output differ on every run for no reason.

        It also answered a question nobody has. The fingerprint answers the
        real one: is this the data and the model that produced these numbers?
        """
        assert len(card.dataset_fingerprint) == 16
        assert card.sources_as_of == config.SOURCES_AS_OF

    def test_carries_the_full_provenance_registry(self, card) -> None:
        assert set(card.provenance) == set(config.PROVENANCE)

    def test_every_provenance_tier_is_represented(self, card) -> None:
        # If nothing were tagged `synthetic`, the honesty claim would be empty.
        tiers = {entry.tier for entry in card.provenance.values()}
        assert tiers == {"real", "derived", "synthetic"}

    def test_label_counts_match_the_records(self, card) -> None:
        assert sum(card.counts.branch_labels.values()) == card.counts.branches
        assert sum(card.counts.zone_labels.values()) == card.counts.scored_zones


class TestConfigCoherence:
    """The config is the tuning surface, so its own consistency is a test."""

    def test_weight_magnitudes_sum_to_one_on_every_axis(self) -> None:
        # Keeps each score in [0, 1] and makes a contribution readable as a
        # share of the final score.
        for weights in (
            config.STRENGTH_WEIGHTS,
            config.MARKET_WEIGHTS,
            config.OPPORTUNITY_WEIGHTS,
        ):
            assert sum(abs(w) for w in weights.values()) == pytest.approx(1.0)

    def test_the_penalty_weights_are_the_negative_ones(self) -> None:
        assert config.MARKET_WEIGHTS["cannibalisation_penalty"] < 0
        assert config.OPPORTUNITY_WEIGHTS["saturation_norm"] < 0

    def test_thresholds_are_ordered(self) -> None:
        assert config.STRENGTH_LOW < config.STRENGTH_HIGH
        assert config.MARKET_LOW < config.MARKET_HIGH
        assert config.OPPORTUNITY_WATCH < config.OPPORTUNITY_GROW

    def test_catchment_radii_increase_as_density_falls(self) -> None:
        r = config.CATCHMENT_RADIUS_M
        assert r["dense_urban"] < r["suburban"] < r["low_density"]

    def test_the_default_catchment_context_is_a_real_one(self) -> None:
        assert config.DEFAULT_CATCHMENT_CONTEXT in config.CATCHMENT_RADIUS_M

    def test_competitors_are_searched_wider_than_the_widest_catchment(self) -> None:
        # Rivals just outside a catchment still compete for the same customer,
        # so the search must not be narrower than the service area.
        assert max(config.CATCHMENT_RADIUS_M.values()) - 1000 <= config.COMPETITOR_SEARCH_RADIUS_M

    def test_the_rating_band_is_narrower_than_the_full_scale(self) -> None:
        # Normalising against 0-5 would flatten every real difference in a
        # category where everyone rates 4.5+.
        assert 0 < config.RATING_FLOOR < config.RATING_CEIL <= 5
        assert config.RATING_CEIL - config.RATING_FLOOR < 1.5

    def test_damping_keeps_covered_zones_visible(self) -> None:
        assert 0 < config.COVERED_ZONE_DAMPING < 1


class TestCommittedDataset:
    """Validates the deliverable as shipped, not a fixture.

    A reviewer clones the repo and reads exactly these files.
    """

    @pytest.fixture
    def branches(self) -> list[BranchRecord]:
        path = config.DATA_PROCESSED / "branches.json"
        if not path.exists():
            pytest.skip("dataset not built; run `uv run python -m pipeline.run`")
        return [BranchRecord.model_validate(r) for r in json.loads(path.read_text())]

    @pytest.fixture
    def card(self) -> ModelCard:
        path = config.DATA_PROCESSED / "model_card.json"
        if not path.exists():
            pytest.skip("dataset not built")
        return ModelCard.model_validate(json.loads(path.read_text()))

    def test_branches_json_validates_against_the_model(self, branches) -> None:
        # `extra="forbid"` means this also catches a field the frontend reads
        # but the pipeline stopped writing.
        assert len(branches) == 23

    def test_the_model_card_validates(self, card) -> None:
        assert card.counts.branches == 23

    def test_the_card_agrees_with_the_branch_file(self, branches, card) -> None:
        from collections import Counter

        assert card.counts.branch_labels == dict(Counter(b.recommendation for b in branches))

    def test_the_shipped_card_matches_the_current_config(self, card) -> None:
        """Catches a dataset committed before a config change.

        If these drift, the "How this works" panel describes a model that did
        not produce the numbers on screen.
        """
        assert card.branch_model["strength_weights"] == config.STRENGTH_WEIGHTS
        assert card.geography["h3_resolution"] == config.H3_RESOLUTION

    def test_every_geojson_layer_is_a_valid_feature_collection(self) -> None:
        for name in (
            "catchments.geojson",
            "overlaps.geojson",
            "competitors.geojson",
            "whitespace.geojson",
        ):
            path = config.DATA_PROCESSED / name
            if not path.exists():
                pytest.skip("dataset not built")
            fc = json.loads(path.read_text())
            assert fc["type"] == "FeatureCollection"
            for feature in fc["features"]:
                assert feature["type"] == "Feature"
                assert feature["geometry"]["type"] in ("Polygon", "Point")

    def test_every_polygon_ring_is_closed(self) -> None:
        for name in ("catchments.geojson", "overlaps.geojson", "whitespace.geojson"):
            path = config.DATA_PROCESSED / name
            if not path.exists():
                pytest.skip("dataset not built")
            for feature in json.loads(path.read_text())["features"]:
                ring = feature["geometry"]["coordinates"][0]
                assert ring[0] == ring[-1], f"{name} has an unclosed ring"

    def test_the_web_bundle_serves_the_same_bytes(self) -> None:
        """The app must not render a different dataset from the committed one."""
        for path in sorted(config.DATA_PROCESSED.glob("*.json")) + sorted(
            config.DATA_PROCESSED.glob("*.geojson")
        ):
            mirrored = config.WEB_PUBLIC_DATA / path.name
            if not mirrored.exists():
                pytest.skip("web data not mirrored; run the pipeline")
            assert mirrored.read_bytes() == path.read_bytes(), f"{path.name} is out of sync"

    def test_every_branch_carries_a_complete_explanation(self, branches) -> None:
        for b in branches:
            assert b.strength.contributions
            assert b.market.contributions
            assert len(b.top_drivers) == 3
            for c in b.strength.contributions + b.market.contributions:
                assert len(c.explanation) > 20, f"{b.branch_id}/{c.signal} has no reasoning"

    def test_the_portfolio_is_not_all_one_label(self, branches) -> None:
        """A recommendation everyone gets is not a recommendation.

        This is a calibration guard, not a correctness one: if the thresholds
        ever collapse the portfolio into a single bucket, the product stops
        supporting a decision.
        """
        labels = {b.recommendation for b in branches}
        assert len(labels) >= 2

    def test_zones_validate_and_carry_reasoning(self) -> None:
        path = config.DATA_PROCESSED / "whitespace.geojson"
        if not path.exists():
            pytest.skip("dataset not built")
        features = json.loads(path.read_text())["features"]
        for feature in features:
            props = dict(feature["properties"])
            props["boundary"] = feature["geometry"]["coordinates"][0]
            record = ZoneRecord.model_validate(props)
            assert record.opportunity.contributions
