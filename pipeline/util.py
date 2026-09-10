"""Small shared helpers: JSON IO, geodesy, normalisation, seeded randomness."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from pipeline import config

EARTH_RADIUS_M = 6_371_008.8


# --------------------------------------------------------------------------
# IO
# --------------------------------------------------------------------------
def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any, *, compact: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        if compact
        else json.dumps(payload, indent=2, ensure_ascii=False)
    )
    path.write_text(text + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Geodesy
# --------------------------------------------------------------------------
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def local_metres_per_degree(lat: float) -> tuple[float, float]:
    """Metres per degree of latitude and longitude at a given latitude.

    Used to work in a locally-flat planar frame. Over a 6 km catchment in the
    UAE the error against a proper projection is well under a percent, which is
    far smaller than the uncertainty in the radius assumption itself.
    """
    m_per_deg_lat = 111_132.92 - 559.82 * math.cos(2 * math.radians(lat))
    m_per_deg_lon = 111_412.84 * math.cos(math.radians(lat))
    return m_per_deg_lat, m_per_deg_lon


def circle_polygon(lat: float, lon: float, radius_m: float) -> list[list[float]]:
    """A closed [lon, lat] ring approximating a circle on the ellipsoid."""
    m_lat, m_lon = local_metres_per_degree(lat)
    steps = config.CATCHMENT_POLYGON_STEPS
    ring = []
    for i in range(steps + 1):
        theta = 2 * math.pi * i / steps
        ring.append(
            [
                round(lon + (radius_m * math.cos(theta)) / m_lon, 6),
                round(lat + (radius_m * math.sin(theta)) / m_lat, 6),
            ]
        )
    return ring


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------
def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def minmax(value: float, floor: float, ceil: float) -> float:
    """Normalise into [0, 1] against an explicit band, not the observed range.

    Explicit bands are deliberate: they keep the score stable when the
    portfolio changes, so a branch's number does not move because a *different*
    branch was added.
    """
    if ceil <= floor:
        return 0.5
    return clamp01((value - floor) / (ceil - floor))


def log_minmax(value: float, floor: float, ceil: float) -> float:
    v = max(value, 1e-9)
    return minmax(math.log(v), math.log(max(floor, 1e-9)), math.log(max(ceil, 1e-9)))


def percentile(sorted_values: list[float], q: float) -> float:
    """Linearly-interpolated quantile of an already-sorted list.

    Written out rather than indexed with `int(q * (n - 1))`, which floors to 0
    for a two-element list and would collapse a normalisation band to zero
    width -- turning a real signal into a constant.
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = clamp01(q) * (len(sorted_values) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def percentile_rank(value: float, population: list[float]) -> float:
    """Share of the population at or below `value`, in [0, 1]."""
    if not population:
        return 0.5
    return sum(1 for p in population if p <= value) / len(population)


# --------------------------------------------------------------------------
# Deterministic pseudo-randomness
# --------------------------------------------------------------------------
def seeded_unit(*parts: Any) -> float:
    """A stable float in [0, 1) derived from the seed and the given key parts.

    Used for every synthetic field so the committed dataset is byte-reproducible
    and a reviewer re-running the pipeline gets the same numbers we shipped.
    """
    key = "|".join([str(config.RANDOM_SEED), *(str(p) for p in parts)])
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def seeded_normal(*parts: Any, mean: float = 0.0, sd: float = 1.0) -> float:
    """Box-Muller from two independent seeded uniforms."""
    u1 = max(seeded_unit(*parts, "u1"), 1e-12)
    u2 = seeded_unit(*parts, "u2")
    z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
    return mean + sd * z
