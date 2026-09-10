"""Catchment construction and self-overlap (cannibalisation) geometry.

DESIGN CHOICE: radius, not isochrone. A drive-time isochrone is the more
faithful catchment and the obvious upgrade, but it needs a routing API, a key
and a per-branch request budget -- and in the UAE the difference matters less
than it would in a European city, because the road network is grid-like and
grade-separated, so a 10-minute drive is close to circular. We ship the radius
baseline, vary it by urban context (config.CATCHMENT_RADIUS_M) so it is not a
single naive number, and name the isochrone upgrade in docs/decisions.md.

Overlap is computed in a locally-flat planar frame centred on each pair, which
keeps shapely's Euclidean area calculation valid at these distances.
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Point, Polygon

from pipeline.util import circle_polygon, haversine_m, local_metres_per_degree


@dataclass
class Catchment:
    branch_id: str
    radius_m: int
    area_km2: float
    ring: list[list[float]]  # GeoJSON [lon, lat] closed ring


@dataclass
class OverlapPair:
    branch_a: str
    branch_b: str
    centroid_distance_m: int
    overlap_area_km2: float
    # Share of A's catchment covered by B, and vice versa. Asymmetric on
    # purpose: a small branch swallowed by a big one is the interesting case.
    share_of_a: float
    share_of_b: float


def build_catchments(branches) -> dict[str, Catchment]:
    out: dict[str, Catchment] = {}
    for b in branches:
        r = b.catchment_radius_m
        out[b.branch_id] = Catchment(
            branch_id=b.branch_id,
            radius_m=r,
            area_km2=round(3.141592653589793 * (r / 1000) ** 2, 3),
            ring=circle_polygon(b.lat, b.lon, r),
        )
    return out


def _planar_circle(lat: float, lon: float, radius_m: float, ref_lat: float, ref_lon: float):
    """The catchment circle as a shapely polygon in metres from a reference point."""
    m_lat, m_lon = local_metres_per_degree(ref_lat)
    x = (lon - ref_lon) * m_lon
    y = (lat - ref_lat) * m_lat
    return Point(x, y).buffer(radius_m, quad_segs=32)


def compute_overlaps(branches) -> list[OverlapPair]:
    """Pairwise self-overlap between our own catchments.

    Only pairs whose catchments can physically intersect are evaluated, so this
    stays O(n^2) on a trivially small n with an early distance reject.
    """
    pairs: list[OverlapPair] = []
    for i, a in enumerate(branches):
        for b in branches[i + 1 :]:
            d = haversine_m(a.lat, a.lon, b.lat, b.lon)
            if d >= a.catchment_radius_m + b.catchment_radius_m:
                continue  # disjoint, nothing to compute
            ref_lat, ref_lon = (a.lat + b.lat) / 2, (a.lon + b.lon) / 2
            pa = _planar_circle(a.lat, a.lon, a.catchment_radius_m, ref_lat, ref_lon)
            pb = _planar_circle(b.lat, b.lon, b.catchment_radius_m, ref_lat, ref_lon)
            inter = pa.intersection(pb)
            if inter.is_empty:
                continue
            area_km2 = inter.area / 1e6
            pairs.append(
                OverlapPair(
                    branch_a=a.branch_id,
                    branch_b=b.branch_id,
                    centroid_distance_m=int(d),
                    overlap_area_km2=round(area_km2, 3),
                    share_of_a=round(inter.area / pa.area, 4),
                    share_of_b=round(inter.area / pb.area, 4),
                )
            )
    return pairs


def cannibalisation_index(branches, overlaps: list[OverlapPair]) -> dict[str, dict]:
    """Per-branch cannibalisation: how much of my catchment do siblings cover?

    We take the *union* of sibling intersections, not the sum, so three
    overlapping siblings covering the same corner are not triple-counted --
    summing is the classic error here and would push a cluster to a false
    SHRINK.
    """
    by_branch: dict[str, list[OverlapPair]] = {b.branch_id: [] for b in branches}
    for p in overlaps:
        by_branch[p.branch_a].append(p)
        by_branch[p.branch_b].append(p)

    index: dict[str, dict] = {}
    lookup = {b.branch_id: b for b in branches}
    for bid, plist in by_branch.items():
        me = lookup[bid]
        mine = _planar_circle(me.lat, me.lon, me.catchment_radius_m, me.lat, me.lon)
        union = None
        neighbours = []
        for p in plist:
            other_id = p.branch_b if p.branch_a == bid else p.branch_a
            other = lookup[other_id]
            poly = _planar_circle(other.lat, other.lon, other.catchment_radius_m, me.lat, me.lon)
            clipped = mine.intersection(poly)
            if clipped.is_empty:
                continue
            union = clipped if union is None else union.union(clipped)
            neighbours.append(
                {
                    "branch_id": other_id,
                    "name": other.name,
                    "distance_m": int(haversine_m(me.lat, me.lon, other.lat, other.lon)),
                    "share_of_my_catchment": round(clipped.area / mine.area, 4),
                }
            )
        covered = 0.0 if union is None else union.area / mine.area
        neighbours.sort(key=lambda n: -n["share_of_my_catchment"])
        index[bid] = {
            "overlapped_share": round(covered, 4),
            "sibling_count": len(neighbours),
            "siblings": neighbours,
        }
    return index


def overlap_features(branches, overlaps: list[OverlapPair]) -> list[dict]:
    """The actual intersection polygons, as GeoJSON features for the map.

    Drawing the overlap *shape* rather than a number is the difference between
    "BD14 is 65% cannibalised" and a decision-maker seeing the wedge of Abu
    Dhabi that three of their own lounges are all paying rent to serve.
    """
    lookup = {b.branch_id: b for b in branches}
    features: list[dict] = []
    for p in overlaps:
        a, b = lookup[p.branch_a], lookup[p.branch_b]
        ref_lat, ref_lon = (a.lat + b.lat) / 2, (a.lon + b.lon) / 2
        pa = _planar_circle(a.lat, a.lon, a.catchment_radius_m, ref_lat, ref_lon)
        pb = _planar_circle(b.lat, b.lon, b.catchment_radius_m, ref_lat, ref_lon)
        inter = pa.intersection(pb)
        if inter.is_empty:
            continue
        m_lat, m_lon = local_metres_per_degree(ref_lat)
        ring = [
            [round(ref_lon + x / m_lon, 6), round(ref_lat + y / m_lat, 6)]
            for x, y in inter.exterior.coords
        ]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {
                    "pair_id": f"{p.branch_a}~{p.branch_b}",
                    "branch_a": p.branch_a,
                    "branch_a_name": a.name,
                    "branch_b": p.branch_b,
                    "branch_b_name": b.name,
                    "centroid_distance_m": p.centroid_distance_m,
                    "overlap_area_km2": p.overlap_area_km2,
                    "share_of_a": p.share_of_a,
                    "share_of_b": p.share_of_b,
                },
            }
        )
    features.sort(key=lambda f: -f["properties"]["overlap_area_km2"])
    return features
