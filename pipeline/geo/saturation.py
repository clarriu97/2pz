"""Competitive saturation and local competitive position, per branch catchment."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from pipeline import config
from pipeline.util import haversine_m


@dataclass
class CatchmentCompetition:
    branch_id: str
    competitor_count: int
    competitors_per_km2: float
    # Saturation normalised against the portfolio, so "saturated" means
    # saturated *relative to where else we trade* -- the comparison a portfolio
    # team actually makes.
    saturation_norm: float
    competitor_mean_rating: float
    competitive_position_stars: float
    premium_share: float
    nearest_competitor_m: int
    top_competitors: list[dict]


def compute_competition(branches, competitors, catchments) -> dict[str, CatchmentCompetition]:
    raw: dict[str, dict] = {}

    for b in branches:
        r = b.catchment_radius_m
        inside = []
        for c in competitors:
            d = haversine_m(b.lat, b.lon, c.lat, c.lon)
            if d <= r:
                inside.append((d, c))
        inside.sort(key=lambda t: t[0])

        area_km2 = catchments[b.branch_id].area_km2
        ratings = [c.rating for _, c in inside]
        raw[b.branch_id] = {
            "count": len(inside),
            "per_km2": len(inside) / area_km2 if area_km2 else 0.0,
            "mean_rating": round(mean(ratings), 3) if ratings else 0.0,
            "premium_share": (
                round(sum(1 for _, c in inside if c.tier == "premium") / len(inside), 3)
                if inside
                else 0.0
            ),
            "nearest_m": int(inside[0][0]) if inside else -1,
            "top": [
                {
                    "competitor_id": c.competitor_id,
                    "name": c.name,
                    "tier": c.tier,
                    "rating": c.rating,
                    "distance_m": int(d),
                }
                for d, c in inside[:8]
            ],
        }

    # Normalise density across the portfolio, not against an absolute constant:
    # what counts as a crowded catchment is market-specific.
    densities = sorted(v["per_km2"] for v in raw.values())
    lo = densities[0]
    # Cap at the 90th percentile so one hyper-dense catchment (Downtown-style)
    # does not compress every other branch into the bottom of the scale.
    hi = densities[max(0, int(0.9 * (len(densities) - 1)))]

    out: dict[str, CatchmentCompetition] = {}
    for b in branches:
        v = raw[b.branch_id]
        sat = 0.5 if hi <= lo else max(0.0, min(1.0, (v["per_km2"] - lo) / (hi - lo)))
        position = round(b.rating - v["mean_rating"], 3) if v["count"] else 0.0
        out[b.branch_id] = CatchmentCompetition(
            branch_id=b.branch_id,
            competitor_count=v["count"],
            competitors_per_km2=round(v["per_km2"], 4),
            saturation_norm=round(sat, 4),
            competitor_mean_rating=v["mean_rating"],
            competitive_position_stars=position,
            premium_share=v["premium_share"],
            nearest_competitor_m=v["nearest_m"],
            top_competitors=v["top"],
        )
    return out


def zone_saturation(competitors, cell_lookup, cell_area_km2: float) -> dict[str, float]:
    """Competitor count per H3 cell, normalised across the gridded metros."""
    import h3

    counts: dict[str, int] = {}
    for c in competitors:
        idx = h3.latlng_to_cell(c.lat, c.lon, config.H3_RESOLUTION)
        if idx in cell_lookup:
            counts[idx] = counts.get(idx, 0) + 1

    if not counts:
        return {idx: 0.0 for idx in cell_lookup}
    densities = sorted(v / cell_area_km2 for v in counts.values())
    hi = densities[max(0, int(0.9 * (len(densities) - 1)))]
    return {
        idx: round(min(1.0, (counts.get(idx, 0) / cell_area_km2) / hi), 4) if hi > 0 else 0.0
        for idx in cell_lookup
    }
