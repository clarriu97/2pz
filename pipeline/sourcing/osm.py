"""Thin Overpass API client with an on-disk cache.

Overpass is free, needs no key and returns real, current OpenStreetMap data,
which is why it is our competitor and activity-density source. Every response
is cached under data/raw/osm/ keyed by a hash of the query, so a reviewer can
re-run the pipeline end to end with no network access at all.
"""

from __future__ import annotations

import hashlib
import time

import httpx

from pipeline import config
from pipeline.util import read_json, write_json

CACHE_DIR = config.DATA_RAW / "osm"
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# The public Overpass instances are a shared free resource with a couple of
# concurrent slots per IP, and they will drop a client that fans out. We keep a
# hard floor between requests and back off generously on failure; the cache
# means a reviewer pays this cost never, and we pay it once.
MIN_REQUEST_INTERVAL_S = 8.0
_last_request_at = 0.0

# When true, a cache miss raises instead of reaching for the network. CI runs
# in this mode: the committed caches are the contract, and a silent fetch
# would turn a missing-cache bug into a green build that only works because
# the runner happened to have internet.
OFFLINE = False


class CacheMiss(RuntimeError):
    """Raised in offline mode when a query has no committed response."""


# Element types we ask for. Deliberately NOT `nwr`: making Overpass compute
# geometric centres for *relations* over a metro-sized bbox reliably times the
# public instances out (504), while node+way returns the same POIs in ~4s.
# Relations are multipolygon administrative/building shapes and contribute
# almost nothing to a POI count.
ELEMENT_TYPES = ("node", "way")


def bbox_query(bbox: tuple[float, float, float, float], selectors: list[str]) -> str:
    """Build an Overpass QL query for a set of tag selectors over a bbox."""
    s, w, n, e = bbox
    parts = ["[out:json][timeout:180];", "("]
    for sel in selectors:
        for etype in ELEMENT_TYPES:
            parts.append(f"{etype}{sel}({s},{w},{n},{e});")
    parts.append(");")
    # `out tags center` gives us tags plus a coordinate for ways without
    # downloading their full node geometry.
    parts.append("out tags center;")
    return "\n".join(parts)


# Branches further apart than this start a new query cluster. 40 km is wider
# than any catchment we model but tight enough to keep Al Ain (130 km from
# Abu Dhabi city) from inflating one bbox to cover the empty desert between
# them -- which is what grouping by emirate would do.
CLUSTER_LINK_DISTANCE_M = 40_000


def cluster_bboxes(branches, pad_m: float) -> dict[str, tuple[float, float, float, float]]:
    """One padded bbox per geographic cluster of branches.

    Single-linkage clustering on great-circle distance: branches within
    CLUSTER_LINK_DISTANCE_M of each other share a bbox. Querying per cluster
    rather than per branch cuts 23 Overpass requests to a handful, and one
    cached response then serves every branch in the cluster.
    """
    from pipeline.util import haversine_m, local_metres_per_degree

    # Union-find over the branch list.
    parent = list(range(len(branches)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(branches):
        for j in range(i + 1, len(branches)):
            b = branches[j]
            if haversine_m(a.lat, a.lon, b.lat, b.lon) <= CLUSTER_LINK_DISTANCE_M:
                parent[find(i)] = find(j)

    groups: dict[int, list] = {}
    for i, b in enumerate(branches):
        groups.setdefault(find(i), []).append(b)

    out: dict[str, tuple[float, float, float, float]] = {}
    for members in groups.values():
        lats = [b.lat for b in members]
        lons = [b.lon for b in members]
        m_lat, m_lon = local_metres_per_degree(sum(lats) / len(lats))
        dlat, dlon = pad_m / m_lat, pad_m / m_lon
        # Name the cluster after its largest branch, so cache filenames and log
        # lines are readable. The branch id is part of the key because
        # emirate+area alone is not unique across clusters: two distant
        # clusters anchored on same-named districts would collide in this dict
        # and one would be silently dropped, along with every competitor
        # around it.
        anchor = max(members, key=lambda b: b.review_count)
        name = f"{anchor.emirate}-{anchor.area}-{anchor.branch_id}".replace(" ", "_")
        out[name] = (
            round(min(lats) - dlat, 4),
            round(min(lons) - dlon, 4),
            round(max(lats) + dlat, 4),
            round(max(lons) + dlon, 4),
        )
    return out


def _query_digest(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]


def _cache_path(query: str, label: str):
    """Where a response is written: a readable label plus the query's digest.

    The digest is what identifies the response; the label is only there so a
    human can tell the cache files apart.
    """
    return CACHE_DIR / f"{label}.{_query_digest(query)}.json"


def _find_cached(query: str):
    """Look a response up by query digest alone, ignoring the label.

    Renaming a cluster (a cosmetic change) must not invalidate a cache that
    took an hour of polite rate-limited requests to fill. Matching on the
    digest means the cache tracks the *query*, which is the thing that
    actually determines the response.
    """
    matches = sorted(CACHE_DIR.glob(f"*.{_query_digest(query)}.json"))
    return matches[0] if matches else None


def overpass(query: str, *, label: str, refresh: bool = False) -> list[dict]:
    """Run an Overpass QL query and return its `elements`, cached by content."""
    path = _cache_path(query, label)
    if not refresh:
        existing = _find_cached(query)
        if existing is not None:
            cached = read_json(existing)
            if cached is not None:
                return cached["elements"]

    global _last_request_at
    if OFFLINE:
        raise CacheMiss(
            f"No committed Overpass response for {label!r} and the pipeline is running "
            f"offline. Run `uv run python -m pipeline.run --refresh` with network access to "
            f"populate {CACHE_DIR}, and commit the result."
        )

    last_error: Exception | None = None
    for endpoint in ENDPOINTS:
        for attempt in range(3):
            wait = MIN_REQUEST_INTERVAL_S - (time.monotonic() - _last_request_at)
            if wait > 0:
                time.sleep(wait)
            _last_request_at = time.monotonic()
            try:
                resp = httpx.post(
                    endpoint,
                    content=query.encode("utf-8"),
                    headers={"Content-Type": "text/plain; charset=utf-8"},
                    timeout=180,
                )
                resp.raise_for_status()
                payload = resp.json()
                write_json(path, payload, compact=True)
                return payload["elements"]
            except Exception as exc:  # rate limit / gateway timeout -> back off
                last_error = exc
                print(
                    f"    overpass attempt {attempt + 1} failed ({type(exc).__name__}), backing off"
                )
                time.sleep(15 * (attempt + 1))
        print(f"  overpass endpoint failed ({endpoint}): {last_error}")
    raise RuntimeError(f"all Overpass endpoints failed for {label}: {last_error}")


def element_coords(el: dict) -> tuple[float, float] | None:
    """Coordinates for a node, or the geometric centre for a way/relation."""
    if "lat" in el and "lon" in el:
        return el["lat"], el["lon"]
    center = el.get("center")
    if center:
        return center["lat"], center["lon"]
    return None
