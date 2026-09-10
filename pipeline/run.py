"""End-to-end offline pipeline.

    uv run python -m pipeline.run              # use cached sources
    uv run python -m pipeline.run --refresh    # re-fetch Nominatim + Overpass
    uv run python -m pipeline.run --notes      # also regenerate AI notes (needs OPENAI_API_KEY)

Writes data/processed/*, then mirrors it into web/public/data/ so the frontend
serves the exact same bytes that are committed and reviewable.

The whole product is a function of this script's output. Nothing is computed in
the browser and nothing is fetched at page load, which is what makes the
deliverable reviewable offline with no keys.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import UTC, datetime

from pipeline import config
from pipeline.geo.catchments import (
    build_catchments,
    cannibalisation_index,
    compute_overlaps,
    overlap_features,
)
from pipeline.geo.saturation import compute_competition, zone_saturation
from pipeline.geo.whitespace import build_zones, catchment_demand
from pipeline.scoring.model import (
    branch_label,
    branch_market,
    branch_strength,
    zone_label,
    zone_opportunity,
)
from pipeline.sourcing.branches import load_branches
from pipeline.sourcing.competitors import load_competitors
from pipeline.sourcing.demand import COMPONENT_WEIGHTS, load_zone_activity
from pipeline.sourcing.osm import cluster_bboxes
from pipeline.util import write_json

# Whitespace cells are only useful to a reviewer if the map stays responsive.
# We keep every cell that carries any signal and drop the empty desert, which
# is thousands of identical SKIP hexes that say nothing.
MIN_ZONE_FEATURES_TO_KEEP = 1


def _confidence(branch, competition) -> dict:
    """Per-branch trust flags, shown in the UI next to the recommendation.

    Caveats are split into ones that should move the confidence *level* and
    ones that are worth stating but not worth downgrading a branch for. Most
    of our coordinates resolve at district rather than unit precision, so
    counting that as a demotion would mark almost the whole portfolio "low"
    and the flag would stop meaning anything.
    """
    major: list[str] = []
    minor: list[str] = []

    if branch.review_count < config.LOW_CONFIDENCE_REVIEW_THRESHOLD:
        major.append(
            f"Only {branch.review_count} reviews — the rating is statistically thin, so both "
            "the quality and the competitive-position signals are noisy here."
        )
    if competition.competitor_count < config.LOW_CONFIDENCE_COMPETITOR_THRESHOLD:
        major.append(
            f"Only {competition.competitor_count} competitors mapped in this catchment. That is "
            "more likely an OpenStreetMap coverage gap than a genuine competitive vacuum, so "
            "treat the headroom score as optimistic."
        )
    if branch.geocode_precision in ("emirate", "manual"):
        major.append(
            "Geocoding could not resolve this address; the coordinate was placed by hand from "
            "the venue's stated location, so the catchment centre may be off by a kilometre or "
            "more."
        )
    elif branch.geocode_precision == "area":
        minor.append(
            "Location resolved to the district rather than the exact unit, so the catchment is "
            "centred within a few hundred metres of the real door — immaterial at a "
            f"{branch.catchment_radius_m / 1000:.1f} km radius."
        )

    level = "high" if not major else ("low" if len(major) >= 2 else "medium")
    return {"level": level, "caveats": major + minor}


def build(*, refresh: bool = False, with_notes: bool = False) -> dict:
    started = datetime.now(UTC)
    print("1/7  branches (real listing + Nominatim geocoding)")
    branches = load_branches(refresh=refresh)
    print(f"     {len(branches)} branches resolved")

    print("2/7  competitors (OpenStreetMap via Overpass)")
    competitors = load_competitors(branches, refresh=refresh)
    print(f"     {len(competitors)} competing venues within "
          f"{config.COMPETITOR_SEARCH_RADIUS_M / 1000:.0f} km of a branch")

    print("3/7  zone activity (OSM built-form demand proxy)")
    bboxes = dict(config.WHITESPACE_BBOXES)
    bboxes.update(cluster_bboxes(branches, config.COMPETITOR_SEARCH_RADIUS_M))
    activity = load_zone_activity(bboxes, refresh=refresh)
    print(f"     {len(activity)} H3 cells carry at least one mapped feature")

    print("4/7  geography (catchments, self-overlap, saturation)")
    catchments = build_catchments(branches)
    overlaps = compute_overlaps(branches)
    cannibalisation = cannibalisation_index(branches, overlaps)
    competition = compute_competition(branches, competitors, catchments)
    branch_demand = catchment_demand(branches, activity)
    print(f"     {len(overlaps)} overlapping catchment pairs")

    print("5/7  whitespace grid")
    zones = build_zones(branches, activity)
    cell_lookup = {z.h3_index: z for z in zones}
    sat = zone_saturation(competitors, cell_lookup, zones[0].area_km2 if zones else 1.0)
    for z in zones:
        z.saturation_norm = sat.get(z.h3_index, 0.0)
    print(f"     {len(zones)} cells gridded across {len(config.WHITESPACE_BBOXES)} metros")

    print("6/7  scoring")
    branch_rows: list[dict] = []
    for b in branches:
        comp = competition[b.branch_id]
        cann = cannibalisation[b.branch_id]
        demand = branch_demand[b.branch_id]

        x = branch_strength(b, comp)
        y = branch_market(b, comp, cann, demand["demand_norm"])
        label, rule = branch_label(x.score, y.score, cann["overlapped_share"])

        merged = x.contributions + y.contributions
        drivers = sorted(merged, key=lambda c: -abs(c.contribution))

        branch_rows.append(
            {
                **b.to_dict(),
                "recommendation": label,
                "decision_rule": rule,
                "strength": x.to_dict(),
                "market": y.to_dict(),
                "top_drivers": [c.signal for c in drivers[:3]],
                "competition": {
                    "competitor_count": comp.competitor_count,
                    "competitors_per_km2": comp.competitors_per_km2,
                    "saturation_norm": comp.saturation_norm,
                    "competitor_mean_rating": comp.competitor_mean_rating,
                    "competitive_position_stars": comp.competitive_position_stars,
                    "premium_share": comp.premium_share,
                    "nearest_competitor_m": comp.nearest_competitor_m,
                    "top_competitors": comp.top_competitors,
                },
                "cannibalisation": cann,
                "demand": demand,
                "catchment_area_km2": catchments[b.branch_id].area_km2,
                "confidence": _confidence(b, comp),
                "analyst_note": None,
            }
        )

    zone_rows: list[dict] = []
    for z in zones:
        score = zone_opportunity(z)
        label, rule = zone_label(z, score.score)
        has_signal = (
            z.residential_count + z.activity_count + z.affluence_count
            >= MIN_ZONE_FEATURES_TO_KEEP
        )
        if not has_signal and label == "SKIP":
            continue
        zone_rows.append(
            {
                "zone_id": z.h3_index,
                "metro": z.metro,
                "lat": z.lat,
                "lon": z.lon,
                "boundary": z.boundary,
                "area_km2": z.area_km2,
                "residential_count": z.residential_count,
                "activity_count": z.activity_count,
                "affluence_count": z.affluence_count,
                "demand_norm": z.demand_norm,
                "coverage_gap_norm": z.coverage_gap_norm,
                "saturation_norm": z.saturation_norm,
                "nearest_branch_id": z.nearest_branch_id,
                "nearest_branch_distance_m": z.nearest_branch_distance_m,
                "inside_own_catchment": z.inside_own_catchment,
                "opportunity": score.to_dict(),
                "recommendation": label,
                "decision_rule": rule,
                "flags": z.flags,
                "analyst_note": None,
            }
        )
    print(f"     {len(branch_rows)} branches, {len(zone_rows)} scored zones "
          f"({len(zones) - len(zone_rows)} empty cells dropped)")

    print("7/7  writing data/processed")
    _write_outputs(branch_rows, zone_rows, competitors, catchments, branches, overlaps, started)

    if with_notes:
        from pipeline.ai.notes import generate_notes

        generate_notes(branch_rows, zone_rows)
        _write_outputs(
            branch_rows, zone_rows, competitors, catchments, branches, overlaps, started
        )

    _mirror_to_web()
    return {"branches": len(branch_rows), "zones": len(zone_rows)}


def _write_outputs(branch_rows, zone_rows, competitors, catchments, branches, overlaps, started):
    P = config.DATA_PROCESSED

    write_json(P / "branches.json", branch_rows)

    write_json(
        P / "catchments.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [catchments[r["branch_id"]].ring]},
                    "properties": {
                        "branch_id": r["branch_id"],
                        "name": r["name"],
                        "radius_m": catchments[r["branch_id"]].radius_m,
                        "urban_context": r["urban_context"],
                        "recommendation": r["recommendation"],
                        "overlapped_share": r["cannibalisation"]["overlapped_share"],
                    },
                }
                for r in branch_rows
            ],
        },
        compact=True,
    )

    write_json(
        P / "overlaps.geojson",
        {"type": "FeatureCollection", "features": overlap_features(branches, overlaps)},
        compact=True,
    )

    write_json(
        P / "competitors.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [c.lon, c.lat]},
                    "properties": {
                        "competitor_id": c.competitor_id,
                        "name": c.name,
                        "category": c.category,
                        "tier": c.tier,
                        "rating": c.rating,
                        "nearest_branch_id": c.nearest_branch_id,
                        "distance_to_nearest_m": c.distance_to_nearest_m,
                    },
                }
                for c in competitors
            ],
        },
        compact=True,
    )

    write_json(
        P / "whitespace.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [z["boundary"]]},
                    "properties": {k: v for k, v in z.items() if k != "boundary"},
                }
                for z in zone_rows
            ],
        },
        compact=True,
    )

    write_json(P / "model_card.json", _model_card(branch_rows, zone_rows, competitors, started))


def _model_card(branch_rows, zone_rows, competitors, started) -> dict:
    """A machine-readable snapshot of exactly how this dataset was produced.

    The frontend renders this in the "How this works" panel and the chat
    endpoint is given it as context, so the parameters a reviewer reads are
    provably the ones that produced the numbers on screen.
    """
    from collections import Counter

    return {
        "generated_at": started.isoformat(),
        "seed": config.RANDOM_SEED,
        "counts": {
            "branches": len(branch_rows),
            "competitors": len(competitors),
            "scored_zones": len(zone_rows),
            "branch_labels": dict(Counter(r["recommendation"] for r in branch_rows)),
            "zone_labels": dict(Counter(z["recommendation"] for z in zone_rows)),
        },
        "geography": {
            "catchment_radius_m": config.CATCHMENT_RADIUS_M,
            "catchment_method": "haversine radius by urban context",
            "h3_resolution": config.H3_RESOLUTION,
            "competitor_search_radius_m": config.COMPETITOR_SEARCH_RADIUS_M,
            "whitespace_metros": list(config.WHITESPACE_BBOXES),
        },
        "branch_model": {
            "strength_weights": config.STRENGTH_WEIGHTS,
            "market_weights": config.MARKET_WEIGHTS,
            "thresholds": {
                "strength_high": config.STRENGTH_HIGH,
                "strength_low": config.STRENGTH_LOW,
                "market_high": config.MARKET_HIGH,
                "market_low": config.MARKET_LOW,
                "cannibalisation_shrink_trigger": config.CANNIBALISATION_SHRINK_TRIGGER,
            },
        },
        "zone_model": {
            "opportunity_weights": config.OPPORTUNITY_WEIGHTS,
            "demand_components": COMPONENT_WEIGHTS,
            "thresholds": {
                "grow": config.OPPORTUNITY_GROW,
                "watch": config.OPPORTUNITY_WATCH,
                "min_demand": config.MIN_DEMAND_FOR_CONSIDERATION,
                "covered_zone_damping": config.COVERED_ZONE_DAMPING,
            },
        },
        "normalisation": {
            "rating_band": [config.RATING_FLOOR, config.RATING_CEIL],
            "review_volume_band": [config.REVIEW_VOLUME_FLOOR, config.REVIEW_VOLUME_CEIL],
            "competitive_position_clip_stars": config.COMPETITIVE_POSITION_CLIP,
        },
        "provenance": config.PROVENANCE,
    }


def _mirror_to_web() -> None:
    dst = config.WEB_PUBLIC_DATA
    dst.mkdir(parents=True, exist_ok=True)
    for src in sorted(config.DATA_PROCESSED.glob("*")):
        if src.is_file():
            shutil.copy2(src, dst / src.name)
    print(f"     mirrored {config.DATA_PROCESSED} -> {dst}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-fetch remote sources")
    ap.add_argument("--notes", action="store_true", help="regenerate AI analyst notes")
    args = ap.parse_args()
    result = build(refresh=args.refresh, with_notes=args.notes)
    print(f"\ndone: {result['branches']} branches, {result['zones']} zones")


if __name__ == "__main__":
    main()
