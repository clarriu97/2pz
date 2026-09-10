"""The invariants the product's honesty rests on.

These are not shape tests. Each one guards a claim the UI makes to a reviewer,
and each would let a confidently wrong recommendation through if it broke.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipeline.models import (
    AxisScore,
    Branch,
    Cannibalisation,
    Catchment,
    Contribution,
    Sibling,
    Zone,
)
from tests.conftest import make_branch, make_zone


def contribution(signal: str = "x", value: float = 0.3, weight: float = 1.0) -> Contribution:
    c = weight * value
    return Contribution(
        signal=signal,
        label=signal,
        raw_value=value,
        raw_display=f"{value}",
        normalised=value,
        weight=weight,
        contribution=c,
        direction="neutral" if abs(c) < 1e-9 else ("up" if c > 0 else "down"),
        explanation="because",
    )


class TestAxisScore:
    """The explainability guarantee: the breakdown must explain the score."""

    def test_accepts_score_equal_to_contribution_sum(self) -> None:
        axis = AxisScore(
            axis="strength",
            score=0.5,
            contributions=[contribution("a", 0.3), contribution("b", 0.2)],
        )
        assert axis.score == pytest.approx(sum(c.contribution for c in axis.contributions))

    def test_rejects_score_that_the_breakdown_does_not_explain(self) -> None:
        # This is the failure that would make the UI lie: a score the listed
        # signals do not add up to.
        with pytest.raises(ValidationError, match="would not explain the score"):
            AxisScore(axis="strength", score=0.9, contributions=[contribution("a", 0.3)])

    def test_tolerates_display_rounding_only(self) -> None:
        AxisScore(axis="s", score=0.3005, contributions=[contribution("a", 0.3)])
        with pytest.raises(ValidationError):
            AxisScore(axis="s", score=0.32, contributions=[contribution("a", 0.3)])

    def test_requires_at_least_one_contribution(self) -> None:
        with pytest.raises(ValidationError):
            AxisScore(axis="strength", score=0.0, contributions=[])

    def test_by_impact_orders_by_absolute_magnitude(self) -> None:
        axis = AxisScore(
            axis="s",
            score=0.1,
            contributions=[
                contribution("small", 0.05),
                contribution("big_negative", 0.4, weight=-1.0),
                contribution("medium", 0.45),
            ],
        )
        # A large negative driver must outrank a small positive one: the
        # question is "what moved this most", not "what helped".
        assert [c.signal for c in axis.by_impact()] == ["medium", "big_negative", "small"]


class TestContribution:
    def test_rejects_direction_contradicting_the_sign(self) -> None:
        with pytest.raises(ValidationError, match="contradicts contribution"):
            Contribution(
                signal="x",
                label="x",
                raw_value=1,
                raw_display="1",
                normalised=1.0,
                weight=-0.2,
                contribution=-0.2,
                direction="up",
                explanation="wrong",
            )

    def test_zero_contribution_is_neutral(self) -> None:
        assert contribution("x", 0.0).direction == "neutral"

    def test_requires_a_non_empty_explanation(self) -> None:
        # An unexplained signal is worse than a missing one: it looks accounted
        # for in the UI while telling the reader nothing.
        with pytest.raises(ValidationError):
            Contribution(
                signal="x",
                label="x",
                raw_value=1,
                raw_display="1",
                normalised=1.0,
                weight=0.2,
                contribution=0.2,
                direction="up",
                explanation="",
            )


class TestBranch:
    def test_rejects_a_malformed_branch_id(self) -> None:
        with pytest.raises(ValidationError):
            make_branch("BRANCH-1")

    def test_rejects_an_out_of_range_rating(self) -> None:
        with pytest.raises(ValidationError):
            make_branch(rating=6.2)

    def test_rejects_an_unknown_urban_context(self) -> None:
        with pytest.raises(ValidationError):
            make_branch(urban_context="rural")

    def test_rejects_unknown_fields(self) -> None:
        # extra="forbid" turns a renamed field into an error here rather than
        # a blank panel in the UI.
        with pytest.raises(ValidationError):
            Branch(**{**make_branch().model_dump(), "revenue": 100_000})

    def test_rejects_coordinates_outside_the_globe(self) -> None:
        with pytest.raises(ValidationError):
            make_branch(lat=95.0)


class TestCannibalisation:
    def test_rejects_a_count_that_disagrees_with_the_list(self) -> None:
        with pytest.raises(ValidationError, match="does not match"):
            Cannibalisation(
                overlapped_share=0.4,
                sibling_count=3,
                siblings=[
                    Sibling(branch_id="BD02", name="n", distance_m=100, share_of_my_catchment=0.4)
                ],
            )

    def test_rejects_a_share_above_one(self) -> None:
        # Summing pairwise overlaps instead of unioning them produces exactly
        # this, so the type refuses it.
        with pytest.raises(ValidationError):
            Cannibalisation(overlapped_share=1.4, sibling_count=0, siblings=[])


class TestCatchment:
    def test_rejects_an_unclosed_ring(self) -> None:
        with pytest.raises(ValidationError, match="not closed"):
            Catchment(
                branch_id="BD01",
                radius_m=2000,
                area_km2=12.5,
                ring=[[55.0, 25.0], [55.1, 25.0], [55.1, 25.1], [55.2, 25.2]],
            )

    def test_rejects_a_ring_with_too_few_positions(self) -> None:
        with pytest.raises(ValidationError, match="at least 4 positions"):
            Catchment(
                branch_id="BD01",
                radius_m=2000,
                area_km2=12.5,
                ring=[[55.0, 25.0], [55.1, 25.0], [55.0, 25.0]],
            )

    def test_accepts_a_closed_ring(self) -> None:
        c = Catchment(
            branch_id="BD01",
            radius_m=2000,
            area_km2=12.5,
            ring=[[55.0, 25.0], [55.1, 25.0], [55.1, 25.1], [55.0, 25.0]],
        )
        assert c.ring[0] == c.ring[-1]


class TestRingValidation:
    """An unclosed GeoJSON ring is silently dropped by some renderers.

    `h3.cell_to_boundary` returns six vertices and no closing repeat, so this
    is a mistake the pipeline can make for real rather than a hypothetical.
    """

    def test_zone_rejects_an_unclosed_boundary(self) -> None:
        with pytest.raises(ValidationError, match="not closed"):
            Zone(
                **{
                    **make_zone().model_dump(exclude={"mapped_feature_count"}),
                    "boundary": [[55.3, 25.2], [55.31, 25.2], [55.31, 25.21], [55.32, 25.22]],
                }
            )

    def test_zone_rejects_a_degenerate_boundary(self) -> None:
        with pytest.raises(ValidationError, match="at least 4 positions"):
            Zone(
                **{
                    **make_zone().model_dump(exclude={"mapped_feature_count"}),
                    "boundary": [[55.3, 25.2], [55.31, 25.2], [55.3, 25.2]],
                }
            )


class TestZone:
    def test_mapped_feature_count_sums_the_components(self) -> None:
        z = make_zone(residential=10, activity=4, affluence=1)
        assert z.mapped_feature_count == 15

    def test_zero_features_is_distinguishable_from_low_demand(self) -> None:
        # "Unknown" and "empty" must not be the same value, or the UI cannot
        # tell the reader which one it is looking at.
        empty = make_zone(residential=0, activity=0, affluence=0, demand=0.0)
        assert empty.mapped_feature_count == 0

    def test_rejects_a_normalised_value_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            Zone(**{**make_zone().model_dump(exclude={"mapped_feature_count"}), "demand_norm": 1.5})
