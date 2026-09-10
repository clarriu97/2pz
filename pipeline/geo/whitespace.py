"""Whitespace grid: H3 cells over the three metros, scored for growth.

Coverage gap is the distance from a cell to our nearest branch, normalised
against that branch's own catchment radius rather than a fixed number of
kilometres. A cell 3 km from a dense-urban branch (2.5 km catchment) is a
genuine gap; the same 3 km from a low-density branch (6 km catchment) is
already served. Normalising by radius is what makes the gap signal mean
"under-served" instead of merely "far".
"""

from __future__ import annotations

from dataclasses import dataclass, field

import h3

from pipeline import config
from pipeline.sourcing.demand import COMPONENT_WEIGHTS
from pipeline.util import clamp01, haversine_m, log_minmax


@dataclass
class Zone:
    h3_index: str
    metro: str
    lat: float
    lon: float
    boundary: list[list[float]]
    area_km2: float
    # Real, from OSM
    residential_count: int
    activity_count: int
    affluence_count: int
    # Derived
    demand_norm: float
    coverage_gap_norm: float
    saturation_norm: float
    nearest_branch_id: str
    nearest_branch_distance_m: int
    inside_own_catchment: bool
    flags: list[str] = field(default_factory=list)


def _cells_for_bbox(bbox: tuple[float, float, float, float]) -> set[str]:
    s, w, n, e = bbox
    poly = h3.LatLngPoly([(s, w), (s, e), (n, e), (n, w), (s, w)])
    return set(h3.polygon_to_cells(poly, config.H3_RESOLUTION))


def build_zones(branches, activity: dict[str, dict]) -> list[Zone]:
    cell_area = h3.average_hexagon_area(config.H3_RESOLUTION, unit="km^2")

    # Every cell in the metro bboxes, whether OSM knows anything there or not:
    # an empty cell must still be visible so the map explains its own gaps.
    cells: dict[str, str] = {}
    for metro, bbox in config.WHITESPACE_BBOXES.items():
        for idx in _cells_for_bbox(bbox):
            cells[idx] = metro

    # Raw composite score per cell, before cross-metro normalisation.
    raw: dict[str, float] = {}
    for idx in cells:
        counts = activity.get(idx, {})
        res = counts.get("residential", 0)
        act = counts.get("activity", 0)
        aff = counts.get("affluence", 0)
        # Log-compress each count: the 50th cafe in a district tells us far
        # less than the 5th, and linear counts would let one mega-mall cell
        # dominate the whole grid.
        raw[idx] = (
            COMPONENT_WEIGHTS["residential"] * log_minmax(res + 1, 1, 400)
            + COMPONENT_WEIGHTS["activity"] * log_minmax(act + 1, 1, 250)
            + COMPONENT_WEIGHTS["affluence"] * log_minmax(aff + 1, 1, 60)
        )

    zones: list[Zone] = []
    for idx, metro in cells.items():
        lat, lon = h3.cell_to_latlng(idx)
        counts = activity.get(idx, {})

        nearest_id, nearest_d, nearest_radius = "", float("inf"), 0
        for b in branches:
            d = haversine_m(lat, lon, b.lat, b.lon)
            if d < nearest_d:
                nearest_id, nearest_d, nearest_radius = b.branch_id, d, b.catchment_radius_m

        inside = nearest_d <= nearest_radius
        # Gap saturates at 2x the nearest catchment radius: beyond that the
        # cell is simply out of network, and further is not more attractive.
        gap = clamp01((nearest_d - nearest_radius) / nearest_radius) if nearest_radius else 0.0

        flags: list[str] = []
        if not counts:
            flags.append("no_osm_features")
        if counts.get("residential", 0) == 0 and counts.get("activity", 0) > 0:
            flags.append("non_residential_zone")

        zones.append(
            Zone(
                h3_index=idx,
                metro=metro,
                lat=round(lat, 6),
                lon=round(lon, 6),
                boundary=[[round(ln, 6), round(lt, 6)] for lt, ln in h3.cell_to_boundary(idx)],
                area_km2=round(cell_area, 3),
                residential_count=counts.get("residential", 0),
                activity_count=counts.get("activity", 0),
                affluence_count=counts.get("affluence", 0),
                demand_norm=round(raw[idx], 4),
                coverage_gap_norm=round(gap, 4),
                saturation_norm=0.0,  # filled in by the caller
                nearest_branch_id=nearest_id,
                nearest_branch_distance_m=int(nearest_d),
                inside_own_catchment=inside,
                flags=flags,
            )
        )
    return zones


def catchment_demand(branches, activity: dict[str, dict]) -> dict[str, dict]:
    """Demand reading for each branch's own catchment.

    We take the H3 cells whose centre falls inside the catchment and average
    their composite demand, rather than summing. Summing would reward a wide
    catchment for being wide -- a low-density branch with a 6 km radius would
    outscore a dense-urban one with 2.5 km purely on area. The decision we are
    informing is "is this ground worth holding", which is about intensity.
    """
    per_branch: dict[str, dict] = {}
    for b in branches:
        cells = []
        for idx, counts in activity.items():
            lat, lon = h3.cell_to_latlng(idx)
            if haversine_m(b.lat, b.lon, lat, lon) <= b.catchment_radius_m:
                cells.append(counts)
        res = sum(c.get("residential", 0) for c in cells)
        act = sum(c.get("activity", 0) for c in cells)
        aff = sum(c.get("affluence", 0) for c in cells)
        n = max(len(cells), 1)
        composite = (
            COMPONENT_WEIGHTS["residential"] * log_minmax(res / n + 1, 1, 400)
            + COMPONENT_WEIGHTS["activity"] * log_minmax(act / n + 1, 1, 250)
            + COMPONENT_WEIGHTS["affluence"] * log_minmax(aff / n + 1, 1, 60)
        )
        per_branch[b.branch_id] = {
            "demand_norm": round(clamp01(composite), 4),
            "cells_in_catchment": len(cells),
            "residential_features": res,
            "activity_features": act,
            "affluence_features": aff,
        }
    return per_branch
