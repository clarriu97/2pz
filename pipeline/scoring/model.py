"""The decision model: signed contributions -> score -> label.

EVERYTHING here is a weighted sum of normalised signals. That is a deliberate
constraint, not a limitation of effort: a portfolio committee has to defend a
lease decision to a CFO, and "the gradient boosting said so" is not a defence.
A weighted sum gives us, for free, the artefact the case study actually asks
for -- a signed contribution breakdown that adds up exactly to the score.

So every score returned from this module carries its own `contributions`:
[{signal, raw_value, normalised, weight, contribution}], where
    sum(contribution) == score
to floating-point tolerance. The UI renders that list directly and the AI
layer is handed the same list, so the map, the tooltip and the analyst can
never disagree about why a branch got its label.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from pipeline import config
from pipeline.util import clamp01, log_minmax, minmax


@dataclass
class Contribution:
    signal: str
    label: str  # human-readable, shown in the UI
    raw_value: float | str
    raw_display: str
    normalised: float
    weight: float
    contribution: float
    direction: str  # "up" | "down" | "neutral"
    explanation: str


@dataclass
class AxisScore:
    axis: str
    score: float
    contributions: list[Contribution] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "axis": self.axis,
            "score": round(self.score, 4),
            "contributions": [asdict(c) for c in self.contributions],
        }


def _mk(
    signal: str,
    label: str,
    raw: float | str,
    raw_display: str,
    normalised: float,
    weight: float,
    explanation: str,
) -> Contribution:
    contribution = weight * normalised
    if abs(contribution) < 1e-9:
        direction = "neutral"
    else:
        direction = "up" if contribution > 0 else "down"
    return Contribution(
        signal=signal,
        label=label,
        raw_value=raw,
        raw_display=raw_display,
        normalised=round(normalised, 4),
        weight=weight,
        contribution=round(contribution, 4),
        direction=direction,
        explanation=explanation,
    )


# --------------------------------------------------------------------------
# Axis X -- branch strength
# --------------------------------------------------------------------------
def branch_strength(branch, competition) -> AxisScore:
    w = config.STRENGTH_WEIGHTS

    rating_n = minmax(branch.rating, config.RATING_FLOOR, config.RATING_CEIL)
    reviews_n = log_minmax(
        branch.review_count, config.REVIEW_VOLUME_FLOOR, config.REVIEW_VOLUME_CEIL
    )
    momentum_n = clamp01(branch.momentum)
    pos = competition.competitive_position_stars
    pos_n = minmax(pos, -config.COMPETITIVE_POSITION_CLIP, config.COMPETITIVE_POSITION_CLIP)

    contributions = [
        _mk(
            "rating_norm",
            "Guest rating",
            branch.rating,
            f"{branch.rating:.1f}★",
            rating_n,
            w["rating_norm"],
            f"{branch.rating:.1f}★ on a {config.RATING_FLOOR}-{config.RATING_CEIL} "
            "market band — category ratings cluster tightly, so we normalise "
            "against the band the market actually occupies, not 0–5.",
        ),
        _mk(
            "review_volume_norm",
            "Review volume (scale proxy)",
            branch.review_count,
            f"{branch.review_count:,} reviews",
            reviews_n,
            w["review_volume_norm"],
            f"{branch.review_count:,} reviews, log-normalised between "
            f"{config.REVIEW_VOLUME_FLOOR} and {config.REVIEW_VOLUME_CEIL}. Stands in for "
            "footfall, which we do not have.",
        ),
        _mk(
            "momentum",
            "Recent momentum",
            round(branch.momentum, 3),
            f"{(branch.momentum - 0.5) * 200:+.0f}% vs own trend",
            momentum_n,
            w["momentum"],
            "Recent-review trend versus the branch's own history. SIMULATED — "
            "the chain does not publish dated review feeds.",
        ),
        _mk(
            "competitive_position",
            "Position vs local rivals",
            pos,
            f"{pos:+.2f}★ vs local mean",
            pos_n,
            w["competitive_position"],
            (
                f"We rate {abs(pos):.2f}★ {'above' if pos >= 0 else 'below'} the "
                f"{competition.competitor_count} rivals inside this catchment "
                f"(their mean {competition.competitor_mean_rating:.2f}★)."
                if competition.competitor_count
                else "No mapped rivals inside the catchment, so this signal is held "
                "neutral rather than scored as a win."
            ),
        ),
    ]
    return AxisScore("strength", sum(c.contribution for c in contributions), contributions)


# --------------------------------------------------------------------------
# Axis Y -- market attractiveness & defensibility
# --------------------------------------------------------------------------
def branch_market(branch, competition, cannibalisation, demand_norm: float) -> AxisScore:
    w = config.MARKET_WEIGHTS

    headroom = 1.0 - competition.saturation_norm
    cann = clamp01(cannibalisation["overlapped_share"])
    top_sibling = (
        cannibalisation["siblings"][0] if cannibalisation.get("siblings") else None
    )

    contributions = [
        _mk(
            "demand_norm",
            "Catchment demand",
            round(demand_norm, 3),
            f"{demand_norm:.0%} of metro peak",
            demand_norm,
            w["demand_norm"],
            "Built-form demand proxy for the catchment: residential, everyday-retail "
            "and premium-venue density from OpenStreetMap. A proxy for spending "
            "power, not a census.",
        ),
        _mk(
            "headroom_norm",
            "Competitive headroom",
            round(competition.competitors_per_km2, 3),
            f"{competition.competitor_count} rivals · "
            f"{competition.competitors_per_km2:.2f}/km²",
            headroom,
            w["headroom_norm"],
            f"{competition.competitor_count} competing venues in the catchment "
            f"({competition.competitors_per_km2:.2f}/km²), "
            f"{competition.saturation_norm:.0%} of the portfolio's saturation ceiling. "
            "Less crowded ground scores higher.",
        ),
        _mk(
            "cannibalisation_penalty",
            "Self-cannibalisation",
            round(cann, 3),
            f"{cann:.0%} of catchment shared",
            cann,
            w["cannibalisation_penalty"],
            (
                f"{cann:.0%} of this catchment is also covered by "
                f"{cannibalisation['sibling_count']} of our own lounges"
                + (
                    f", chiefly {top_sibling['name']} at {top_sibling['distance_m'] / 1000:.1f} km."
                    if top_sibling
                    else "."
                )
                if cann > 0
                else "No other Bedashing catchment reaches this area — no self-overlap."
            ),
        ),
    ]
    return AxisScore("market", sum(c.contribution for c in contributions), contributions)


# --------------------------------------------------------------------------
# Label mapping
# --------------------------------------------------------------------------
def branch_label(strength: float, market: float, cannibalisation: float) -> tuple[str, str]:
    """Map the two axes onto PROTECT / HOLD / SHRINK, and say which rule fired.

    The returned rule string is shown verbatim in the UI, so the reviewer sees
    the exact branch of logic that produced the label rather than inferring it.
    """
    if strength >= config.STRENGTH_HIGH and market >= config.MARKET_HIGH:
        return "PROTECT", (
            f"strength {strength:.2f} ≥ {config.STRENGTH_HIGH} AND market "
            f"{market:.2f} ≥ {config.MARKET_HIGH}"
        )
    if strength < config.STRENGTH_LOW:
        return "SHRINK", f"strength {strength:.2f} < {config.STRENGTH_LOW}"
    if market < config.MARKET_LOW and cannibalisation >= config.CANNIBALISATION_SHRINK_TRIGGER:
        return "SHRINK", (
            f"market {market:.2f} < {config.MARKET_LOW} AND self-overlap "
            f"{cannibalisation:.0%} ≥ {config.CANNIBALISATION_SHRINK_TRIGGER:.0%}"
        )
    return "HOLD", (
        f"strength {strength:.2f} and market {market:.2f} fall between the "
        f"PROTECT and SHRINK thresholds"
    )


# --------------------------------------------------------------------------
# Whitespace opportunity
# --------------------------------------------------------------------------
def zone_opportunity(zone) -> AxisScore:
    w = config.OPPORTUNITY_WEIGHTS
    contributions = [
        _mk(
            "demand_norm",
            "Zone demand",
            round(zone.demand_norm, 3),
            f"{zone.demand_norm:.0%} of metro peak",
            zone.demand_norm,
            w["demand_norm"],
            f"{zone.residential_count} residential, {zone.activity_count} everyday-retail "
            f"and {zone.affluence_count} premium features mapped in this "
            f"{zone.area_km2:.1f} km² cell.",
        ),
        _mk(
            "coverage_gap_norm",
            "Coverage gap",
            zone.nearest_branch_distance_m,
            f"{zone.nearest_branch_distance_m / 1000:.1f} km to nearest lounge",
            zone.coverage_gap_norm,
            w["coverage_gap_norm"],
            f"Nearest Bedashing lounge is {zone.nearest_branch_distance_m / 1000:.1f} km away, "
            f"{'inside' if zone.inside_own_catchment else 'beyond'} its catchment. "
            "Gap is measured against that branch's own radius, so 'far' means "
            "under-served rather than merely distant.",
        ),
        _mk(
            "saturation_norm",
            "Competitive saturation",
            round(zone.saturation_norm, 3),
            f"{zone.saturation_norm:.0%} of grid ceiling",
            zone.saturation_norm,
            w["saturation_norm"],
            "Density of competing salons and spas already trading in this cell.",
        ),
    ]
    score = sum(c.contribution for c in contributions)

    if zone.inside_own_catchment:
        damped = score * config.COVERED_ZONE_DAMPING
        contributions.append(
            _mk(
                "covered_zone_damping",
                "Already inside our catchment",
                config.COVERED_ZONE_DAMPING,
                f"score × {config.COVERED_ZONE_DAMPING}",
                1.0,
                round(damped - score, 4),
                "This cell is already served by an existing lounge, so opening here "
                "would mostly move revenue rather than add it. Damped, not deleted, "
                "so the map still shows why it was passed over.",
            )
        )
        score = damped

    return AxisScore("opportunity", score, contributions)


def zone_label(zone, score: float) -> tuple[str, str]:
    if zone.demand_norm < config.MIN_DEMAND_FOR_CONSIDERATION:
        return "SKIP", (
            f"demand {zone.demand_norm:.2f} < floor "
            f"{config.MIN_DEMAND_FOR_CONSIDERATION} — empty ground scores well on "
            "coverage gap and must not surface as an opportunity"
        )
    if zone.inside_own_catchment:
        if score >= config.OPPORTUNITY_WATCH:
            return "WATCH", (
                f"attractive ({score:.2f}) but already inside "
                f"{zone.nearest_branch_id}'s catchment — relocation or capacity, "
                "not a new site"
            )
        return "SKIP", f"already covered by {zone.nearest_branch_id} and score {score:.2f} is low"
    if score >= config.OPPORTUNITY_GROW:
        return "GROW", f"opportunity {score:.2f} ≥ {config.OPPORTUNITY_GROW} with a real gap"
    if score >= config.OPPORTUNITY_WATCH:
        return "WATCH", f"opportunity {score:.2f} ≥ {config.OPPORTUNITY_WATCH}"
    return "SKIP", f"opportunity {score:.2f} < {config.OPPORTUNITY_WATCH}"
