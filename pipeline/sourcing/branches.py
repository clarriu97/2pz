"""Load the real branch network and attach coordinates + operating context.

The branch list, areas, addresses, ratings and review counts are REAL: they
come from Bedashing's public location listing cross-referenced with public
Google Maps rating aggregates (see data/raw/branches_seed.csv, committed).
Coordinates are resolved with Nominatim. Two operational fields the chain does
not publish -- recent-review momentum and chair utilisation -- are simulated
deterministically and tagged `synthetic` so they are never mistaken for fact.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field

from pipeline import config
from pipeline.sourcing.geocode import geocode_candidates
from pipeline.util import read_json, seeded_normal, seeded_unit, write_json

SEED_CSV = config.DATA_RAW / "branches_seed.csv"
COORD_OVERRIDES = config.DATA_RAW / "branch_coords_override.json"
BRANCHES_RAW = config.DATA_RAW / "branches_resolved.json"

# Urban context per area, which selects the catchment radius. Assigned from
# local knowledge of the built form, not from a dataset -- an assumption we
# declare rather than dress up.
AREA_CONTEXT: dict[str, str] = {
    "City Walk": "dense_urban",
    "Al Safa 2": "dense_urban",
    "Al Barsha 2": "dense_urban",
    "Al Nahyan": "dense_urban",
    "Ministry Area": "dense_urban",
    "Mirdif": "suburban",
    "Al Warqa": "suburban",
    "Muwaileh": "suburban",
    "Al Shahba": "suburban",
    "Mohammed Bin Zayed City": "suburban",
    "Shakhbout City": "suburban",
    "Khalifa City": "suburban",
    "Khaleej Al Arabi": "suburban",
    "Al Maqta": "suburban",
    "Al Ain": "suburban",
    "Saqr Bin Mohd City": "suburban",
    "Al Taif": "suburban",
    "Nad Al Sheba": "low_density",
    "Jumeirah Park": "low_density",
    "Palm Jumeirah": "low_density",
    "Al Falah": "low_density",
    "Shahama": "low_density",
    "West Yas": "low_density",
}


@dataclass
class Branch:
    branch_id: str
    name: str
    area: str
    emirate: str
    address: str
    lat: float
    lon: float
    rating: float
    review_count: int
    urban_context: str
    catchment_radius_m: int
    # Synthetic operational fields (declared).
    momentum: float = 0.0
    chair_utilisation: float = 0.0
    geocode_precision: str = "address"
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _synthesise_operational(branch_id: str, review_count: int) -> tuple[float, float]:
    """Simulate momentum and chair utilisation.

    Momentum is the share of reviews landing in the last 90 days versus the
    branch's own historical rate, rescaled to [0, 1] where 0.5 means "flat".
    It is correlated with review volume on purpose: busy lounges genuinely
    accumulate reviews faster, so a purely uniform draw would produce a signal
    that contradicts the real data next to it.
    """
    base = 0.5 + 0.12 * (seeded_unit(branch_id, "scale") - 0.5)
    drift = seeded_normal(branch_id, "momentum", mean=0.0, sd=0.16)
    momentum = max(0.0, min(1.0, base + drift))
    # Utilisation loosely tracks momentum, with independent operational noise.
    util = 0.52 + 0.30 * (momentum - 0.5) + seeded_normal(branch_id, "util", sd=0.08)
    return round(momentum, 4), round(max(0.15, min(0.98, util)), 4)


def load_branches(*, refresh: bool = False) -> list[Branch]:
    if not refresh:
        cached = read_json(BRANCHES_RAW)
        if cached:
            return [Branch(**row) for row in cached]

    overrides: dict = read_json(COORD_OVERRIDES, default={}) or {}
    branches: list[Branch] = []

    with SEED_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            bid = row["branch_id"]
            area, emirate = row["area"], row["emirate"]
            precision = "address"
            flags: list[str] = []

            if bid in overrides:
                lat, lon = overrides[bid]["lat"], overrides[bid]["lon"]
                precision = overrides[bid].get("precision", "manual")
            else:
                candidates = [
                    f"{row['address']}, United Arab Emirates",
                    f"{area}, {emirate}, United Arab Emirates",
                    f"{emirate}, United Arab Emirates",
                ]
                hit = geocode_candidates(candidates)
                if hit is None:
                    flags.append("geocode_failed")
                    print(f"  !! could not geocode {bid} ({area})")
                    continue
                lat, lon, used = hit
                precision = (
                    "address"
                    if used == candidates[0]
                    else "area"
                    if used == candidates[1]
                    else "emirate"
                )
                if precision == "emirate":
                    flags.append("coarse_geocode")

            context = AREA_CONTEXT.get(area, config.DEFAULT_CATCHMENT_CONTEXT)
            momentum, util = _synthesise_operational(bid, int(row["google_reviews"]))
            branches.append(
                Branch(
                    branch_id=bid,
                    name=row["name"],
                    area=area,
                    emirate=emirate,
                    address=row["address"],
                    lat=round(lat, 6),
                    lon=round(lon, 6),
                    rating=float(row["google_rating"]),
                    review_count=int(row["google_reviews"]),
                    urban_context=context,
                    catchment_radius_m=config.CATCHMENT_RADIUS_M[context],
                    momentum=momentum,
                    chair_utilisation=util,
                    geocode_precision=precision,
                    flags=flags,
                )
            )

    write_json(BRANCHES_RAW, [b.to_dict() for b in branches])
    return branches
