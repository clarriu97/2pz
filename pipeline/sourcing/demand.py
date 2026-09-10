"""Zone demand proxy built from real OpenStreetMap activity density.

WHY THIS PROXY. The signal we actually want is "how much latent spend on
premium beauty services sits in this zone" -- a function of resident
population, daytime population and affluence. None of those is available
free at neighbourhood granularity for the UAE. Rather than download a
population raster and pretend it captures affluence (a labourer camp and a
villa district have similar population density and wildly different spend), we
build the proxy from what OSM *does* know reliably in the Gulf: the built
environment.

Three real components, combined with declared weights:

  residential  -- apartment/residential buildings and residential POIs:
                  where customers sleep.
  activity     -- everyday retail and services (cafes, pharmacies, clinics,
                  supermarkets, schools): where footfall happens.
  affluence    -- hotels, malls, fitness centres, private clinics, marinas:
                  the best free discriminator of premium spending power.

This is honest about what it is: a built-form proxy, not a census. Its
limitation -- that it under-reads brand-new districts OSM has not mapped yet --
is stated in the README trust section and surfaced per zone as a confidence
flag.
"""

from __future__ import annotations

import h3

from pipeline import config
from pipeline.sourcing.osm import bbox_query, element_coords, overpass
from pipeline.util import read_json, write_json

DEMAND_RAW = config.DATA_RAW / "zone_activity_counts.json"

# Component weights. Affluence is weighted heavily relative to its raw count
# because it is the scarcest and most discriminating signal for a luxury
# service; residential carries the base of the demand pool.
COMPONENT_WEIGHTS = {"residential": 0.40, "activity": 0.25, "affluence": 0.35}

SELECTORS = {
    "residential": [
        '["building"="apartments"]',
        '["building"="residential"]',
        '["landuse"="residential"]',
        '["place"~"^(neighbourhood|suburb|quarter)$"]',
    ],
    "activity": [
        # Clinics are deliberately absent here and counted under `affluence`
        # instead: private healthcare is a better affluence marker than a
        # footfall one, and a feature is only ever counted in one component.
        '["amenity"~"^(cafe|restaurant|pharmacy|bank|school|kindergarten)$"]',
        '["shop"~"^(supermarket|convenience|clothes|bakery)$"]',
    ],
    "affluence": [
        '["tourism"="hotel"]',
        '["shop"="mall"]',
        '["leisure"="fitness_centre"]',
        '["amenity"="marketplace"]',
        '["leisure"="marina"]',
        '["healthcare"="clinic"]',
    ],
}


def load_zone_activity(
    bboxes: dict[str, tuple[float, float, float, float]], *, refresh: bool = False
) -> dict[str, dict]:
    """Per-H3-cell counts of each component, over every requested bbox.

    We collect activity over the union of the whitespace metro boxes AND the
    branch clusters, so a branch outside the three gridded metros (Al Ain,
    Fujairah, Ras Al Khaimah) still gets a real demand reading for its own
    catchment even though we do not offer it as growth territory.

    Returns {h3_index: {"metro": str, "residential": int, "activity": int,
    "affluence": int}}.
    """
    if not refresh:
        cached = read_json(DEMAND_RAW)
        if cached:
            return cached

    cells: dict[str, dict] = {}
    # The whitespace metro boxes and the branch-cluster boxes overlap heavily
    # (the Dubai grid sits inside the Dubai cluster). Without deduplicating by
    # OSM id, every feature in an overlap would be counted once per bbox and
    # those cells would read as twice as dense as they are.
    seen: set[tuple[str, int]] = set()

    for region, bbox in bboxes.items():
        for component, selectors in SELECTORS.items():
            elements = overpass(
                bbox_query(bbox, selectors),
                label=f"demand.{region.lower().replace(' ', '_')}.{component}",
                refresh=refresh,
            )
            fresh = 0
            for el in elements:
                key = (el["type"], el["id"])
                if key in seen:
                    continue
                seen.add(key)
                coords = element_coords(el)
                if coords is None:
                    continue
                idx = h3.latlng_to_cell(coords[0], coords[1], config.H3_RESOLUTION)
                cell = cells.setdefault(
                    idx,
                    {"metro": region, "residential": 0, "activity": 0, "affluence": 0},
                )
                cell[component] += 1
                fresh += 1
            print(f"    {region}/{component}: {len(elements)} features, {fresh} new")

    write_json(DEMAND_RAW, cells, compact=True)
    return cells
