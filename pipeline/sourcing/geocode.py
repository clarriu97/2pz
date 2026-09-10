"""Address -> coordinate resolution via OpenStreetMap Nominatim.

Nominatim is free and needs no key, which keeps the whole pipeline
reproducible by a reviewer. It is also rate-limited to ~1 req/s and does not
know UAE shop-unit addresses, so we:

  1. cache every lookup to data/raw/geocode_cache.json (committed), and
  2. try progressively coarser queries, falling back from the full address to
     "<area>, <emirate>, UAE".

A branch resolved only at area level is still accurate to a few hundred metres,
which is inside the noise of a 2.5-6 km catchment assumption.
"""

from __future__ import annotations

import time

import httpx

from pipeline import config
from pipeline.util import read_json, write_json

CACHE_PATH = config.DATA_RAW / "geocode_cache.json"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "bedashing-network-intelligence/0.1 (case study; contact via repo)"

# UAE bounding box, so Nominatim cannot resolve "Al Ain" to New Zealand.
VIEWBOX = "51.0,22.5,56.6,26.2"


def _query(client: httpx.Client, q: str) -> tuple[float, float] | None:
    resp = client.get(
        NOMINATIM,
        params={
            "q": q,
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": "ae",
            "viewbox": VIEWBOX,
            "bounded": 1,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    hits = resp.json()
    if not hits:
        return None
    return float(hits[0]["lat"]), float(hits[0]["lon"])


def geocode_candidates(candidates: list[str]) -> tuple[float, float, str] | None:
    """Resolve the first candidate query that hits. Returns (lat, lon, query)."""
    cache: dict = read_json(CACHE_PATH, default={}) or {}
    for q in candidates:
        if q in cache:
            hit = cache[q]
            if hit is not None:
                return hit["lat"], hit["lon"], q
            continue

    from pipeline.sourcing import osm

    if osm.OFFLINE:
        raise osm.CacheMiss(
            f"No committed geocode for {candidates[0]!r} and the pipeline is running "
            f"offline. Run with --refresh to populate {CACHE_PATH}, and commit the result."
        )

    with httpx.Client(follow_redirects=True) as client:
        for q in candidates:
            if q in cache:
                continue
            try:
                found = _query(client, q)
            except Exception as exc:  # network hiccup: do not poison the cache
                print(f"    geocode error for {q!r}: {exc}")
                continue
            cache[q] = {"lat": found[0], "lon": found[1]} if found else None
            write_json(CACHE_PATH, cache)
            time.sleep(1.1)  # Nominatim usage policy
            if found:
                return found[0], found[1], q
    return None
