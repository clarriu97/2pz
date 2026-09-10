"""Zone demand proxy built from real OpenStreetMap built-form density.

WHY THIS PROXY. The signal we actually want is "how much latent spend on
premium beauty services sits in this zone" -- a function of resident
population, daytime population and affluence. None of those is available free
at neighbourhood granularity for the UAE. Rather than download a population
raster and pretend it captures affluence (a labour accommodation block and a
villa district have similar population density and wildly different spend on a
premium blow-dry), we build the proxy from what OSM *does* know reliably in the
Gulf: the built environment.

Three real components, combined with declared weights:

  residential  -- apartment/residential buildings and residential land use:
                  where customers sleep.
  activity     -- everyday retail and services (cafes, pharmacies,
                  supermarkets, schools): where footfall happens.
  affluence    -- hotels, malls, fitness centres, private clinics, marinas:
                  the best free discriminator of premium spending power, and
                  therefore the most heavily weighted.

This is honest about what it is: a built-form proxy, not a census. Its
limitation -- that it under-reads brand-new districts OSM has not mapped yet --
is stated in the README trust section and surfaced per zone as a flag.

SOURCING CHANNEL. This layer reads a downloaded OSM extract rather than the
Overpass API. Overpass is right for the competitor layer -- five small bbox
queries -- and wrong for this one, which needs every residential building,
shop and hotel across three metros. Asking a shared free query service for
tens of thousands of features is slow, antisocial, and in practice gets the
client rate-limited into a 406. See `pipeline/sourcing/extract.py`.

Only the aggregate is committed: per-H3-cell counts, a few hundred kilobytes.
The 250 MB extract is gitignored and re-downloadable, so a re-run and CI read
the aggregate and never need it.
"""

from __future__ import annotations

import h3

from pipeline import config
from pipeline.models import ZoneActivity
from pipeline.sourcing.extract import ensure_extract, stream_features
from pipeline.util import read_json, write_json

DEMAND_RAW = config.DATA_RAW / "zone_activity_counts.json"

# Component weights. Affluence is weighted highest relative to its raw count
# because it is the scarcest and most discriminating signal for a luxury
# service; residential carries the base of the demand pool.
COMPONENT_WEIGHTS = {"residential": 0.40, "activity": 0.25, "affluence": 0.35}

# Every tag we fetch, in one list. `bbox_query` expands each into node+way
# forms; a single request per region returns all of them.
SELECTORS = [
    # residential
    '["building"="apartments"]',
    '["building"="residential"]',
    '["landuse"="residential"]',
    '["place"~"^(neighbourhood|suburb|quarter)$"]',
    # activity
    '["amenity"~"^(cafe|restaurant|pharmacy|bank|school|kindergarten)$"]',
    '["shop"~"^(supermarket|convenience|clothes|bakery)$"]',
    # affluence
    '["tourism"="hotel"]',
    '["shop"="mall"]',
    '["leisure"~"^(fitness_centre|marina)$"]',
    '["healthcare"="clinic"]',
    '["amenity"="marketplace"]',
]

# Local classification, checked in this order. A feature lands in exactly one
# component, so nothing is double-counted -- affluence is tested first because
# a mall or hotel is a premium signal even though it is also retail.
_AFFLUENCE = {
    ("tourism", "hotel"),
    ("shop", "mall"),
    ("leisure", "fitness_centre"),
    ("leisure", "marina"),
    ("healthcare", "clinic"),
    ("amenity", "marketplace"),
}
_RESIDENTIAL = {
    ("building", "apartments"),
    ("building", "residential"),
    ("landuse", "residential"),
    ("place", "neighbourhood"),
    ("place", "suburb"),
    ("place", "quarter"),
}
_ACTIVITY = {
    ("amenity", "cafe"),
    ("amenity", "restaurant"),
    ("amenity", "pharmacy"),
    ("amenity", "bank"),
    ("amenity", "school"),
    ("amenity", "kindergarten"),
    ("shop", "supermarket"),
    ("shop", "convenience"),
    ("shop", "clothes"),
    ("shop", "bakery"),
}


def classify(tags: dict) -> str | None:
    """Which demand component this OSM feature counts towards, if any."""
    pairs = set(tags.items())
    if pairs & _AFFLUENCE:
        return "affluence"
    if pairs & _RESIDENTIAL:
        return "residential"
    if pairs & _ACTIVITY:
        return "activity"
    return None


def merge_bboxes(
    bboxes: dict[str, tuple[float, float, float, float]],
) -> dict[str, tuple[float, float, float, float]]:
    """Collapse overlapping regions into their union.

    The whitespace metro boxes and the branch-cluster boxes overlap heavily
    (the Dubai grid sits almost entirely inside the Dubai cluster). Querying
    both would fetch the same features twice and double the request budget for
    nothing.
    """
    items = [(name, list(box)) for name, box in bboxes.items()]
    merged: list[tuple[list[str], list[float]]] = []

    for name, box in items:
        for names, existing in merged:
            overlaps = (
                box[0] <= existing[2]
                and existing[0] <= box[2]
                and box[1] <= existing[3]
                and existing[1] <= box[3]
            )
            if overlaps:
                existing[0] = min(existing[0], box[0])
                existing[1] = min(existing[1], box[1])
                existing[2] = max(existing[2], box[2])
                existing[3] = max(existing[3], box[3])
                names.append(name)
                break
        else:
            merged.append(([name], box))

    # A merge can make two previously-disjoint boxes overlap, so settle.
    changed = True
    while changed:
        changed = False
        for i in range(len(merged)):
            for j in range(i + 1, len(merged)):
                a, b = merged[i][1], merged[j][1]
                if a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                    a[0], a[1] = min(a[0], b[0]), min(a[1], b[1])
                    a[2], a[3] = max(a[2], b[2]), max(a[3], b[3])
                    merged[i][0].extend(merged[j][0])
                    merged.pop(j)
                    changed = True
                    break
            if changed:
                break

    return {"+".join(sorted(names)): tuple(box) for names, box in merged}  # type: ignore[misc]


def load_zone_activity(
    bboxes: dict[str, tuple[float, float, float, float]], *, refresh: bool = False
) -> dict[str, ZoneActivity]:
    """Per-H3-cell counts of each demand component.

    We collect over the union of the whitespace metro boxes AND the branch
    clusters, so a branch outside the three gridded metros (Al Ain, Fujairah,
    Ras Al Khaimah) still gets a real demand reading for its own catchment even
    though we do not offer it as growth territory.

    Returns {h3_index: ZoneActivity}.
    """
    if not refresh:
        cached = read_json(DEMAND_RAW)
        if cached:
            return {idx: ZoneActivity.model_validate(row) for idx, row in cached.items()}

    from pipeline.sourcing import osm

    if osm.OFFLINE:
        raise osm.CacheMiss(
            f"No committed demand aggregate at {DEMAND_RAW} and the pipeline is running "
            "offline. Run `uv run python -m pipeline.run --refresh` with network access to "
            "download the OSM extract and rebuild it, then commit the result."
        )

    regions = merge_bboxes(bboxes)
    print(f"    {len(bboxes)} regions merged to {len(regions)} bounding boxes")

    path = ensure_extract()
    features = stream_features(path, list(regions.values()), classify)

    cells: dict[str, ZoneActivity] = {}
    tally = {"residential": 0, "activity": 0, "affluence": 0}
    for component, lat, lon in features:
        idx = h3.latlng_to_cell(lat, lon, config.H3_RESOLUTION)
        cell = cells.setdefault(idx, ZoneActivity(region=_region_for(lat, lon, bboxes)))
        setattr(cell, component, getattr(cell, component) + 1)
        tally[component] += 1

    print(
        f"    {len(cells)} cells: {tally['residential']} residential, "
        f"{tally['activity']} activity, {tally['affluence']} affluence"
    )

    write_json(DEMAND_RAW, {idx: cell.model_dump() for idx, cell in cells.items()}, compact=True)
    return cells


def _region_for(
    lat: float, lon: float, bboxes: dict[str, tuple[float, float, float, float]]
) -> str:
    """The first named region containing this point, for readable output."""
    for name, (s, w, n, e) in bboxes.items():
        if s <= lat <= n and w <= lon <= e:
            return name
    return "unknown"
