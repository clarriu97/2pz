"""Real competitor salons, spas and hairdressers from OpenStreetMap.

What is real: the existence, name and location of every competitor.
What is simulated: their star rating. OSM carries no ratings and the Google
Places rating for thousands of rivals is not free to obtain, so we draw a
rating per competitor from a plausible category distribution, seeded by the
competitor's OSM id. This matters because the branch score uses
`competitive_position` (our rating minus the local rival mean), so the
*relative* comparison is partly simulated -- and that is called out in the UI
and in the README's trust section rather than hidden.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from pipeline import config
from pipeline.sourcing.osm import bbox_query, cluster_bboxes, element_coords, overpass
from pipeline.util import read_json, seeded_normal, write_json

COMPETITORS_RAW = config.DATA_RAW / "competitors_resolved.json"

# The competitive set: places a Bedashing customer could plausibly choose
# instead. Nail bars and hairdressers compete for the same discretionary spend.
OSM_SELECTORS = [
    '["shop"="beauty"]',
    '["shop"="hairdresser"]',
    '["shop"="massage"]',
    '["leisure"="spa"]',
    '["amenity"="spa"]',
]

# Premium signals in an OSM tag set, used to segment rivals into tiers. A
# lounge competing with hotel spas faces different pressure than one competing
# with walk-in barbershops.
PREMIUM_HINTS = ("spa", "lounge", "luxury", "salon & spa", "wellness", "clinic")


@dataclass
class Competitor:
    competitor_id: str
    name: str
    lat: float
    lon: float
    category: str
    tier: str
    rating: float  # SYNTHETIC
    nearest_branch_id: str
    distance_to_nearest_m: int

    def to_dict(self) -> dict:
        return asdict(self)


def _category(tags: dict) -> str:
    if tags.get("leisure") == "spa" or tags.get("amenity") == "spa":
        return "spa"
    shop = tags.get("shop", "")
    return {"beauty": "beauty_salon", "hairdresser": "hairdresser", "massage": "massage"}.get(
        shop, "other"
    )


def _tier(name: str, tags: dict, category: str) -> str:
    blob = f"{name} {tags.get('description','')}".lower()
    if category == "spa" or any(h in blob for h in PREMIUM_HINTS):
        return "premium"
    if category == "hairdresser":
        return "value"
    return "mid"


# Rating priors per tier: mean and spread, in stars. Premium venues rate a
# little higher and more consistently; value barbershops spread wider.
TIER_RATING_PRIOR = {
    "premium": (4.55, 0.22),
    "mid": (4.35, 0.32),
    "value": (4.15, 0.42),
}


def load_competitors(branches, *, refresh: bool = False) -> list[Competitor]:
    if not refresh:
        cached = read_json(COMPETITORS_RAW)
        if cached:
            return [Competitor(**row) for row in cached]

    from pipeline.util import haversine_m

    # One padded bbox per emirate, then filter to what is actually within
    # COMPETITOR_SEARCH_RADIUS_M of a branch. Fetching a slightly wider net and
    # trimming locally is cheaper and kinder to the public Overpass instances
    # than 23 separate radius queries.
    elements: list[dict] = []
    for emirate, bbox in cluster_bboxes(branches, config.COMPETITOR_SEARCH_RADIUS_M).items():
        label = "competitors." + emirate.lower().replace(" ", "_")
        batch = overpass(bbox_query(bbox, OSM_SELECTORS), label=label, refresh=refresh)
        print(f"    {emirate}: {len(batch)} candidate venues in bbox")
        elements.extend(batch)

    seen: set[str] = set()
    out: list[Competitor] = []
    for el in elements:
        coords = element_coords(el)
        if coords is None:
            continue
        cid = f"{el['type'][0]}{el['id']}"
        if cid in seen:
            continue
        seen.add(cid)
        lat, lon = coords
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:en") or "Unnamed salon (OSM)"
        category = _category(tags)
        tier = _tier(name, tags, category)
        mean, sd = TIER_RATING_PRIOR[tier]
        rating = round(max(3.0, min(5.0, seeded_normal(cid, "rating", mean=mean, sd=sd))), 2)

        nearest_id, nearest_d = "", 10**9
        for b in branches:
            d = haversine_m(lat, lon, b.lat, b.lon)
            if d < nearest_d:
                nearest_id, nearest_d = b.branch_id, d
        if nearest_d > config.COMPETITOR_SEARCH_RADIUS_M:
            continue  # inside the bbox but not near any branch we trade from

        out.append(
            Competitor(
                competitor_id=cid,
                name=name,
                lat=round(lat, 6),
                lon=round(lon, 6),
                category=category,
                tier=tier,
                rating=rating,
                nearest_branch_id=nearest_id,
                distance_to_nearest_m=int(nearest_d),
            )
        )

    write_json(COMPETITORS_RAW, [c.to_dict() for c in out])
    return out
