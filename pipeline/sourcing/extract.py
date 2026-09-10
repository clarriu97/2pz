"""Bulk OpenStreetMap sourcing from a downloaded regional extract.

WHY A SECOND OSM PATH. `pipeline/sourcing/osm.py` queries the public Overpass
API, which is the right tool for the competitor layer: five small bbox queries
whose responses cache to a few hundred kilobytes. It is the wrong tool for the
demand layer, which needs every residential building, shop and hotel across
three metros — tens of thousands of features. Asking a shared free query
service for that, repeatedly, is both slow and antisocial, and in practice it
gets the client rate-limited into a 406.

So bulk goes through a bulk channel: one Geofabrik extract, downloaded once to
`data/raw/extracts/` (gitignored, ~250 MB) and streamed locally with
pyosmium. Only the aggregate it produces -- per-H3-cell counts, a few hundred
kilobytes -- is committed, which is what a re-run and CI actually read.

The distinction is deliberate rather than accidental: targeted queries over the
network, bulk counts from a local extract.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from pipeline import config

# The only OSM keys any demand component looks at. Pre-filtering on these in
# pyosmium's C++ layer is the difference between a minute and a quarter of an
# hour: without it, every one of ~30 million objects in the extract is
# materialised into a Python dict just to be discarded.
DEMAND_KEYS = (
    "building",
    "landuse",
    "place",
    "amenity",
    "shop",
    "tourism",
    "leisure",
    "healthcare",
)

# The smallest Geofabrik extract that contains the whole UAE. There is no
# UAE-only extract, so this also covers the rest of the GCC; the bbox filter
# below discards everything outside our metros.
EXTRACT_URL = "https://download.geofabrik.de/asia/gcc-states-latest.osm.pbf"
EXTRACT_DIR = config.DATA_RAW / "extracts"
EXTRACT_PATH = EXTRACT_DIR / "gcc-states.osm.pbf"


def ensure_extract(*, path: Path | None = None, url: str = EXTRACT_URL) -> Path:
    """Download the extract if it is not already on disk. Returns its path."""
    target = path or EXTRACT_PATH
    if target.exists() and target.stat().st_size > 1_000_000:
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"    downloading {url}")
    with httpx.stream("GET", url, follow_redirects=True, timeout=600) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        written = 0
        # Write to a temporary name and move on success, so an interrupted
        # download can never be mistaken for a complete one on the next run.
        partial = target.with_suffix(".partial")
        with partial.open("wb") as fh:
            for chunk in response.iter_bytes(chunk_size=1 << 20):
                fh.write(chunk)
                written += len(chunk)
                if total and written % (32 << 20) < (1 << 20):
                    print(f"      {written / 1e6:.0f} / {total / 1e6:.0f} MB")
        partial.replace(target)
    print(f"    extract ready: {target.stat().st_size / 1e6:.0f} MB")
    return target


def in_any_bbox(lat: float, lon: float, bboxes: list[tuple[float, float, float, float]]) -> bool:
    """Whether a coordinate falls inside any (min_lat, min_lon, max_lat, max_lon)."""
    return any(s <= lat <= n and w <= lon <= e for s, w, n, e in bboxes)


def stream_features(
    path: Path,
    bboxes: list[tuple[float, float, float, float]],
    classify,
) -> list[tuple[str, float, float]]:
    """Stream the extract, returning (component, lat, lon) for every wanted feature.

    Two passes, deliberately, because the obvious single-pass approach does not
    fit in memory. Ways do not carry coordinates, and pyosmium's
    `with_locations()` builds an index of *every* node in the file -- roughly
    30 million for the GCC extract -- to resolve them. That index is gigabytes
    for a signal we only need to bucket into 5 km hexes.

    Instead:
      pass 1  keep matching nodes outright, and for each matching way record
              only the reference of its first node;
      pass 2  look up the locations of just those referenced nodes.

    Using a way's first node rather than its true centroid is exact enough: it
    is a point on the building's own footprint, and the output is a count per
    ~5 km cell. Residential buildings and land-use polygons are ways, and they
    carry 40% of the demand weight, so skipping ways entirely was not an
    option.
    """
    from collections import defaultdict

    import osmium

    node_features: list[tuple[str, float, float]] = []
    # node ref -> the components of every way whose first node it is. Two
    # adjacent buildings can share a corner node, and a plain dict would keep
    # one and silently drop the rest.
    needed_nodes: defaultdict[int, list[str]] = defaultdict(list)
    way_count = 0

    key_filter = osmium.filter.KeyFilter(*DEMAND_KEYS)

    for obj in osmium.FileProcessor(path).with_filter(key_filter):
        component = classify(dict(obj.tags))
        if component is None:
            continue

        kind = obj.type_str()
        if kind == "n":
            lat, lon = obj.location.lat, obj.location.lon
            if in_any_bbox(lat, lon, bboxes):
                node_features.append((component, lat, lon))
        elif kind == "w" and len(obj.nodes) > 0:
            needed_nodes[obj.nodes[0].ref].append(component)
            way_count += 1

    print(
        f"    pass 1: {len(node_features)} matching nodes in bbox, "
        f"{way_count} matching ways to resolve"
    )

    way_features: list[tuple[str, float, float]] = []
    for obj in osmium.FileProcessor(path).with_filter(osmium.filter.EntityFilter(osmium.osm.NODE)):
        components = needed_nodes.get(obj.id)
        if not components:
            continue
        lat, lon = obj.location.lat, obj.location.lon
        if in_any_bbox(lat, lon, bboxes):
            way_features.extend((component, lat, lon) for component in components)

    print(f"    pass 2: {len(way_features)} ways placed inside a bbox")
    return node_features + way_features
