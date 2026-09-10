"""Single source of truth for every tunable in the decision model.

Nothing in this repository hard-codes a weight, threshold, radius or grid
resolution anywhere else. When a reviewer asks "what drove this number?", this
file is the answer, and `pipeline/run.py` stamps a copy of it into
`data/processed/model_card.json` so the frontend can show the exact
parameterisation that produced the committed data.
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
WEB_PUBLIC_DATA = ROOT / "web" / "public" / "data"

# Deterministic synthesis: every synthetic field is a pure function of this
# seed plus the branch/zone id, so the committed dataset is reproducible.
RANDOM_SEED = 20260910

# --------------------------------------------------------------------------
# Geography
# --------------------------------------------------------------------------
# Catchment radius per urban context, in metres. A salon visit is a
# discretionary, planned trip: UAE customers drive, so we assume a wider
# catchment than a European high-street equivalent. Dense mixed-use districts
# get a tighter radius because the local resident pool is larger and rivals
# are closer; low-density villa districts get a wider one because customers
# already expect to drive.
CATCHMENT_RADIUS_M: dict[str, int] = {
    "dense_urban": 2500,
    "suburban": 4000,
    "low_density": 6000,
}
DEFAULT_CATCHMENT_CONTEXT = "suburban"

# Number of vertices used when approximating a catchment circle as a polygon.
CATCHMENT_POLYGON_STEPS = 64

# H3 resolution for the whitespace grid. Res 7 ~= 5.16 km^2 per hex
# (~1.4 km edge), which is roughly one neighbourhood in a UAE metro — the
# granularity at which a portfolio team actually argues about a site.
H3_RESOLUTION = 7

# Metro bounding boxes we grid for whitespace, as (min_lat, min_lon, max_lat,
# max_lon). We deliberately restrict growth analysis to the three metros where
# the chain has enough presence for the comparison to mean something.
WHITESPACE_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "Dubai": (24.85, 55.05, 25.35, 55.55),
    "Abu Dhabi": (24.30, 54.30, 24.60, 54.80),
    "Sharjah": (25.25, 55.35, 25.45, 55.60),
}

# Competitors are searched within this radius of each branch (metres). Wider
# than the catchment so we also see rivals just outside our service area who
# still compete for the same customer.
COMPETITOR_SEARCH_RADIUS_M = 5000

# --------------------------------------------------------------------------
# Branch decision model  (see docs/decisions.md for the rationale)
# --------------------------------------------------------------------------
# X axis: BRANCH STRENGTH — how well this branch performs, as a business.
# Weights are signed and sum to 1.0 in magnitude so the score lands in [0, 1]
# and each contribution reads directly as "share of the final score".
STRENGTH_WEIGHTS: dict[str, float] = {
    "rating_norm": 0.30,  # absolute service quality
    "review_volume_norm": 0.25,  # log reviews -> proxy for footfall/scale
    "momentum": 0.20,  # recent-review trend -> is it improving?
    "competitive_position": 0.25,  # our rating minus the local rival mean
}

# Y axis: MARKET ATTRACTIVENESS & DEFENSIBILITY — is the ground worth holding?
MARKET_WEIGHTS: dict[str, float] = {
    "demand_norm": 0.45,  # latent demand in the catchment
    "headroom_norm": 0.35,  # 1 - competitive saturation
    "cannibalisation_penalty": -0.20,  # negative: our own branches overlapping
}

# Label mapping on the 2-axis matrix. Tuned so the 23-branch portfolio splits
# into a reviewable spread rather than 21 HOLDs — a recommendation everyone
# gets is not a recommendation.
STRENGTH_HIGH = 0.58
STRENGTH_LOW = 0.42
MARKET_HIGH = 0.55
MARKET_LOW = 0.40

# A branch with weak fundamentals in a weak market is a SHRINK candidate even
# if it clears STRENGTH_LOW, provided it is heavily cannibalised by our own
# network. This is the "we are competing with ourselves" exit.
CANNIBALISATION_SHRINK_TRIGGER = 0.45

# --------------------------------------------------------------------------
# Whitespace decision model
# --------------------------------------------------------------------------
OPPORTUNITY_WEIGHTS: dict[str, float] = {
    "demand_norm": 0.45,
    "coverage_gap_norm": 0.35,
    "saturation_norm": -0.20,
}

# A zone already inside one of our catchments cannot be whitespace, however
# attractive: opening there would cannibalise. We damp its score rather than
# dropping it, so the map still shows *why* it was excluded.
COVERED_ZONE_DAMPING = 0.35

OPPORTUNITY_GROW = 0.62
OPPORTUNITY_WATCH = 0.45

# Zones below this demand floor are dismissed regardless of score: empty
# desert scores well on "coverage gap" and must not surface as an opportunity.
MIN_DEMAND_FOR_CONSIDERATION = 0.12

# --------------------------------------------------------------------------
# Signal normalisation
# --------------------------------------------------------------------------
# Ratings in this category cluster tightly in 4.4-4.9, so normalising against
# the theoretical 0-5 range would flatten every difference to noise. We
# normalise against the band the market actually occupies.
RATING_FLOOR = 4.20
RATING_CEIL = 4.95

# Competitive position: our rating minus the local competitor mean, clipped to
# this band before normalisation. +-0.5 stars is a decisive local gap.
COMPETITIVE_POSITION_CLIP = 0.50

# Review volume is normalised on a log scale between these bounds.
REVIEW_VOLUME_FLOOR = 30
REVIEW_VOLUME_CEIL = 1500

# --------------------------------------------------------------------------
# Confidence model — how much to trust a given row
# --------------------------------------------------------------------------
# Below this review count the rating is statistically thin and we flag the
# branch as low confidence in the UI rather than silently scoring it.
LOW_CONFIDENCE_REVIEW_THRESHOLD = 120
# A catchment with fewer than this many mapped competitors makes the
# competitive-position signal unreliable (OSM coverage gap, not a real vacuum).
LOW_CONFIDENCE_COMPETITOR_THRESHOLD = 3

# --------------------------------------------------------------------------
# AI layer
# --------------------------------------------------------------------------
OPENAI_NOTES_MODEL = "gpt-4.1-mini"
OPENAI_CHAT_MODEL = "gpt-4.1-mini"
NOTES_MAX_WORDS = 60

# --------------------------------------------------------------------------
# Data provenance registry
# --------------------------------------------------------------------------
# Every field the product shows is tagged with where it came from. The UI
# renders these badges so a reviewer never has to guess whether a number is
# real, derived or simulated. This registry is the contract.
PROVENANCE: dict[str, dict[str, str]] = {
    "branch.name": {"tier": "real", "source": "Bedashing public location listing"},
    "branch.area": {"tier": "real", "source": "Bedashing public location listing"},
    "branch.emirate": {"tier": "real", "source": "Bedashing public location listing"},
    "branch.address": {"tier": "real", "source": "Bedashing public location listing"},
    "branch.lat_lng": {"tier": "real", "source": "OpenStreetMap Nominatim geocoding"},
    "branch.rating": {"tier": "real", "source": "Public Google Maps rating aggregate"},
    "branch.review_count": {"tier": "real", "source": "Public Google Maps rating aggregate"},
    "competitor.location": {
        "tier": "real",
        "source": "OpenStreetMap (shop=beauty|hairdresser|massage, leisure/amenity=spa)",
    },
    "competitor.name": {"tier": "real", "source": "OpenStreetMap"},
    "zone.demand": {
        "tier": "derived",
        "source": "OSM residential + retail + premium-venue density, log-normalised",
    },
    "catchment": {
        "tier": "derived",
        "source": "Haversine radius by urban context (config.CATCHMENT_RADIUS_M)",
    },
    "overlap": {
        "tier": "derived",
        "source": "Union of pairwise catchment intersections",
    },
    "saturation": {"tier": "derived", "source": "Competitor count per catchment km^2"},
    "branch.momentum": {
        "tier": "synthetic",
        "source": "Simulated recent-review trend (seeded)",
    },
    "competitor.rating": {
        "tier": "synthetic",
        "source": "Simulated from a per-tier rating prior (seeded)",
    },
    "branch.chair_utilisation": {
        "tier": "synthetic",
        "source": "Simulated operational metric (seeded)",
    },
}
