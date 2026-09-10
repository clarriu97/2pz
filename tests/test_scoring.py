"""The decision model.

Two kinds of assertion here. The boundary tests pin the label mapping at its
thresholds, because an off-by-one there silently reclassifies a lease. The
monotonicity tests pin the *direction* of every signal: if better ratings ever
started lowering a score, every explanation in the product would be a lie while
still adding up correctly.
"""

from __future__ import annotations

import pytest

from pipeline import config
from pipeline.scoring.model import (
    branch_label,
    branch_market,
    branch_strength,
    zone_label,
    zone_opportunity,
)
from tests.conftest import make_branch, make_cannibalisation, make_competition, make_zone


class TestBranchStrength:
    def test_contributions_cover_every_configured_weight(self, branch, competition) -> None:
        axis = branch_strength(branch, competition)
        assert {c.signal for c in axis.contributions} == set(config.STRENGTH_WEIGHTS)

    def test_score_equals_the_sum_of_contributions(self, branch, competition) -> None:
        axis = branch_strength(branch, competition)
        assert axis.score == pytest.approx(
            sum(c.contribution for c in axis.contributions), abs=1e-9
        )

    def test_score_is_bounded_by_the_weights(self, branch, competition) -> None:
        axis = branch_strength(branch, competition)
        assert 0.0 <= axis.score <= sum(config.STRENGTH_WEIGHTS.values())

    def test_a_better_rating_raises_the_score(self, competition) -> None:
        low = branch_strength(make_branch(rating=4.3), competition).score
        high = branch_strength(make_branch(rating=4.9), competition).score
        assert high > low

    def test_more_reviews_raise_the_score(self, competition) -> None:
        low = branch_strength(make_branch(review_count=40), competition).score
        high = branch_strength(make_branch(review_count=1200), competition).score
        assert high > low

    def test_winning_locally_raises_the_score(self, branch) -> None:
        losing = branch_strength(branch, make_competition(position=-0.4)).score
        winning = branch_strength(branch, make_competition(position=0.4)).score
        assert winning > losing

    def test_competitive_position_saturates_at_the_configured_clip(self, branch) -> None:
        # Beyond the clip the signal must stop moving, otherwise one freak
        # local comparison dominates the whole axis.
        at_clip = branch_strength(
            branch, make_competition(position=config.COMPETITIVE_POSITION_CLIP)
        ).score
        beyond = branch_strength(branch, make_competition(position=2.0)).score
        assert beyond == pytest.approx(at_clip)

    def test_an_empty_catchment_holds_position_neutral_rather_than_scoring_a_win(
        self, branch
    ) -> None:
        """No mapped rivals is missing data, not a victory.

        Scoring it as a win would reward branches in areas OpenStreetMap has
        not covered — exactly backwards.
        """
        axis = branch_strength(branch, make_competition(count=0, position=0.0, mean_rating=0.0))
        position = next(c for c in axis.contributions if c.signal == "competitive_position")
        assert position.normalised == pytest.approx(0.5)
        assert "held neutral" in position.explanation

    def test_every_contribution_carries_a_display_value_and_reasoning(
        self, branch, competition
    ) -> None:
        for c in branch_strength(branch, competition).contributions:
            assert c.raw_display.strip()
            assert len(c.explanation) > 20


class TestBranchMarket:
    def test_contributions_cover_every_configured_weight(self, branch, competition) -> None:
        axis = branch_market(branch, competition, make_cannibalisation(), 0.5)
        assert {c.signal for c in axis.contributions} == set(config.MARKET_WEIGHTS)

    def test_more_demand_raises_the_score(self, branch, competition) -> None:
        low = branch_market(branch, competition, make_cannibalisation(), 0.1).score
        high = branch_market(branch, competition, make_cannibalisation(), 0.9).score
        assert high > low

    def test_more_saturation_lowers_the_score(self, branch) -> None:
        roomy = branch_market(
            branch, make_competition(saturation=0.1), make_cannibalisation(), 0.5
        ).score
        crowded = branch_market(
            branch, make_competition(saturation=0.9), make_cannibalisation(), 0.5
        ).score
        assert crowded < roomy

    def test_self_overlap_lowers_the_score(self, branch, competition) -> None:
        clean = branch_market(branch, competition, make_cannibalisation(0.0), 0.5).score
        overlapped = branch_market(
            branch, competition, make_cannibalisation(0.8, siblings=2), 0.5
        ).score
        assert overlapped < clean

    def test_the_cannibalisation_contribution_is_signed_negative(self, branch, competition) -> None:
        axis = branch_market(branch, competition, make_cannibalisation(0.6, siblings=2), 0.5)
        penalty = next(c for c in axis.contributions if c.signal == "cannibalisation_penalty")
        assert penalty.contribution < 0
        assert penalty.direction == "down"

    def test_no_overlap_says_so_in_plain_language(self, branch, competition) -> None:
        axis = branch_market(branch, competition, make_cannibalisation(0.0), 0.5)
        penalty = next(c for c in axis.contributions if c.signal == "cannibalisation_penalty")
        assert "No other Bedashing catchment" in penalty.explanation

    def test_the_top_sibling_is_named_in_the_explanation(self, branch, competition) -> None:
        axis = branch_market(branch, competition, make_cannibalisation(0.6, siblings=2), 0.5)
        penalty = next(c for c in axis.contributions if c.signal == "cannibalisation_penalty")
        assert "Sibling" in penalty.explanation


class TestBranchLabel:
    def test_strong_and_attractive_is_protect(self) -> None:
        label, rule = branch_label(0.8, 0.8, 0.0)
        assert label == "PROTECT"
        assert "PROTECT" not in rule  # the rule states the arithmetic, not the label
        assert str(config.STRENGTH_HIGH) in rule

    def test_weak_is_shrink_regardless_of_market(self) -> None:
        assert branch_label(config.STRENGTH_LOW - 0.01, 0.95, 0.0)[0] == "SHRINK"

    def test_middling_is_hold(self) -> None:
        assert branch_label(0.5, 0.5, 0.0)[0] == "HOLD"

    def test_at_the_protect_boundary_the_label_is_protect(self) -> None:
        # Thresholds are inclusive; pinning that stops a refactor flipping a
        # branch on the boundary.
        assert branch_label(config.STRENGTH_HIGH, config.MARKET_HIGH, 0.0)[0] == "PROTECT"

    def test_just_below_the_protect_boundary_is_hold(self) -> None:
        assert branch_label(config.STRENGTH_HIGH - 1e-9, config.MARKET_HIGH, 0.0)[0] == "HOLD"

    def test_at_the_shrink_boundary_the_label_is_not_shrink(self) -> None:
        assert branch_label(config.STRENGTH_LOW, 0.5, 0.0)[0] == "HOLD"

    def test_a_decent_branch_in_a_weak_market_shrinks_when_heavily_cannibalised(self) -> None:
        """The "we are competing with ourselves" exit.

        A branch can clear the strength floor and still be the wrong branch to
        keep, because our own network already covers its ground.
        """
        strength = (config.STRENGTH_LOW + config.STRENGTH_HIGH) / 2
        weak_market = config.MARKET_LOW - 0.01
        label, rule = branch_label(strength, weak_market, config.CANNIBALISATION_SHRINK_TRIGGER)
        assert label == "SHRINK"
        assert "self-overlap" in rule

    def test_the_same_branch_holds_when_it_is_not_cannibalised(self) -> None:
        strength = (config.STRENGTH_LOW + config.STRENGTH_HIGH) / 2
        assert branch_label(strength, config.MARKET_LOW - 0.01, 0.0)[0] == "HOLD"

    def test_every_label_reports_the_rule_that_fired(self) -> None:
        for args in [(0.9, 0.9, 0.0), (0.1, 0.9, 0.0), (0.5, 0.1, 0.9), (0.5, 0.5, 0.0)]:
            _, rule = branch_label(*args)
            assert len(rule) > 10


class TestZoneOpportunity:
    def test_contributions_cover_every_configured_weight(self, zone) -> None:
        axis = zone_opportunity(zone)
        assert set(config.OPPORTUNITY_WEIGHTS) <= {c.signal for c in axis.contributions}

    def test_score_equals_the_sum_of_contributions(self, zone) -> None:
        axis = zone_opportunity(zone)
        assert axis.score == pytest.approx(
            sum(c.contribution for c in axis.contributions), abs=1e-9
        )

    def test_more_demand_raises_the_score(self) -> None:
        assert (
            zone_opportunity(make_zone(demand=0.9)).score
            > zone_opportunity(make_zone(demand=0.1)).score
        )

    def test_a_bigger_coverage_gap_raises_the_score(self) -> None:
        assert (
            zone_opportunity(make_zone(gap=0.9)).score > zone_opportunity(make_zone(gap=0.1)).score
        )

    def test_more_saturation_lowers_the_score(self) -> None:
        assert (
            zone_opportunity(make_zone(saturation=0.9)).score
            < zone_opportunity(make_zone(saturation=0.1)).score
        )

    def test_a_covered_cell_is_damped_not_deleted(self) -> None:
        open_ground = zone_opportunity(make_zone(inside=False))
        covered = zone_opportunity(make_zone(inside=True))
        assert covered.score == pytest.approx(
            open_ground.score * config.COVERED_ZONE_DAMPING, abs=1e-3
        )

    def test_the_damping_appears_as_its_own_visible_contribution(self) -> None:
        """The map has to be able to explain its own gaps.

        Filtering covered cells out would be cleaner code and a worse product:
        a reviewer asking "why isn't Downtown an opportunity?" deserves to see
        the reason rather than infer it from an absence.
        """
        axis = zone_opportunity(make_zone(inside=True))
        damping = next(c for c in axis.contributions if c.signal == "covered_zone_damping")
        assert damping.contribution < 0
        assert "already served" in damping.explanation

    def test_an_uncovered_cell_has_no_damping_row(self) -> None:
        axis = zone_opportunity(make_zone(inside=False))
        assert all(c.signal != "covered_zone_damping" for c in axis.contributions)


class TestZoneLabel:
    def test_high_score_with_a_real_gap_is_grow(self) -> None:
        label, _ = zone_label(make_zone(demand=0.9), config.OPPORTUNITY_GROW)
        assert label == "GROW"

    def test_mid_score_is_watch(self) -> None:
        label, _ = zone_label(make_zone(demand=0.9), config.OPPORTUNITY_WATCH)
        assert label == "WATCH"

    def test_low_score_is_skip(self) -> None:
        label, _ = zone_label(make_zone(demand=0.9), config.OPPORTUNITY_WATCH - 0.01)
        assert label == "SKIP"

    def test_empty_ground_is_skipped_however_well_it_scores(self) -> None:
        """Empty desert scores beautifully on coverage gap.

        Without the demand floor, the top of the growth shortlist would be
        sand — the single most embarrassing failure this product could have in
        front of a portfolio team.
        """
        label, rule = zone_label(
            make_zone(demand=config.MIN_DEMAND_FOR_CONSIDERATION - 0.01, gap=1.0), 0.99
        )
        assert label == "SKIP"
        assert "must not surface as an opportunity" in rule

    def test_an_attractive_covered_cell_is_watch_not_grow(self) -> None:
        # Already inside our own catchment: a relocation or capacity question,
        # never a new site.
        label, rule = zone_label(make_zone(demand=0.9, inside=True), 0.9)
        assert label == "WATCH"
        assert "relocation or capacity" in rule

    def test_an_unattractive_covered_cell_is_skip(self) -> None:
        label, rule = zone_label(make_zone(demand=0.9, inside=True), 0.1)
        assert label == "SKIP"
        assert "already covered" in rule

    def test_the_demand_floor_takes_precedence_over_coverage(self) -> None:
        label, rule = zone_label(make_zone(demand=0.0, inside=True), config.OPPORTUNITY_GROW + 0.1)
        assert label == "SKIP"
        assert "floor" in rule
