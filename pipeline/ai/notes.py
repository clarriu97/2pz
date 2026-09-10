"""Offline generation of grounded analyst notes.

WHY OFFLINE. Notes are generated once at build time and committed to
data/processed/. That means:
  - a reviewer with no API key still sees the full AI layer working, and
  - the notes are deterministic across a demo, so nothing changes under us
    live on a call.

The cost of the pre-generation is that notes go stale if the model or config
changes -- so each note is stamped with a hash of the payload it was generated
from, and a note whose hash no longer matches is reported as stale rather than
shown as current.
"""

from __future__ import annotations

import hashlib
import json
import os

from pipeline import config
from pipeline.ai.prompts import BRANCH_USER, NOTES_SYSTEM, ZONE_USER
from pipeline.util import read_json, write_json

CACHE_PATH = config.DATA_PROCESSED / "analyst_notes.json"

# Notes are only worth generating where a human would actually read one. 23
# branches, plus every zone that is not a foregone SKIP.
ZONE_LABELS_WORTH_A_NOTE = {"GROW", "WATCH"}


def _fingerprint(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _contribution_lines(contributions: list[dict]) -> str:
    """Render a contribution breakdown as the model sees it: signed and ordered."""
    rows = sorted(contributions, key=lambda c: -abs(c["contribution"]))
    return "\n".join(
        f"  - {c['label']}: {c['raw_display']} -> normalised {c['normalised']:.2f} "
        f"x weight {c['weight']:+.2f} = {c['contribution']:+.3f}"
        for c in rows
    )


def branch_payload(row: dict) -> str:
    siblings = row["cannibalisation"]["siblings"][:3]
    sibling_lines = (
        "\n".join(
            f"  - {s['name']} at {s['distance_m'] / 1000:.1f} km covers "
            f"{s['share_of_my_catchment']:.0%} of this catchment"
            for s in siblings
        )
        or "  - none"
    )
    caveats = row["confidence"]["caveats"]
    caveat_lines = "\n".join(f"  - {c}" for c in caveats) or "  - none"
    return BRANCH_USER.format(
        name=row["name"],
        area=row["area"],
        emirate=row["emirate"],
        recommendation=row["recommendation"],
        decision_rule=row["decision_rule"],
        strength_score=row["strength"]["score"],
        strength_lines=_contribution_lines(row["strength"]["contributions"]),
        market_score=row["market"]["score"],
        market_lines=_contribution_lines(row["market"]["contributions"]),
        radius_m=row["catchment_radius_m"],
        urban_context=row["urban_context"],
        catchment_area_km2=row["catchment_area_km2"],
        competitor_count=row["competition"]["competitor_count"],
        competitor_mean_rating=row["competition"]["competitor_mean_rating"],
        overlapped_share=row["cannibalisation"]["overlapped_share"],
        sibling_count=row["cannibalisation"]["sibling_count"],
        sibling_lines=sibling_lines,
        confidence_level=row["confidence"]["level"],
        caveat_lines=caveat_lines,
    )


def zone_payload(row: dict, branch_names: dict[str, str]) -> str:
    return ZONE_USER.format(
        zone_id=row["zone_id"],
        metro=row["metro"],
        recommendation=row["recommendation"],
        decision_rule=row["decision_rule"],
        score=row["opportunity"]["score"],
        lines=_contribution_lines(row["opportunity"]["contributions"]),
        area_km2=row["area_km2"],
        residential_count=row["residential_count"],
        activity_count=row["activity_count"],
        affluence_count=row["affluence_count"],
        nearest_branch_name=branch_names.get(row["nearest_branch_id"], row["nearest_branch_id"]),
        distance_km=row["nearest_branch_distance_m"] / 1000,
        covered="inside its catchment" if row["inside_own_catchment"] else "beyond its catchment",
    )


def generate_notes(branch_rows: list[dict], zone_rows: list[dict]) -> dict:
    """Fill `analyst_note` on every row, generating only what is missing or stale."""
    cache: dict = read_json(CACHE_PATH, default={}) or {}
    branch_names = {r["branch_id"]: r["name"] for r in branch_rows}

    jobs: list[tuple[str, str, dict]] = []
    for row in branch_rows:
        jobs.append((f"branch:{row['branch_id']}", branch_payload(row), row))
    for row in zone_rows:
        if row["recommendation"] in ZONE_LABELS_WORTH_A_NOTE:
            jobs.append((f"zone:{row['zone_id']}", zone_payload(row, branch_names), row))

    todo = [(k, p, r) for k, p, r in jobs if cache.get(k, {}).get("fingerprint") != _fingerprint(p)]
    print(f"     {len(jobs)} notes total, {len(todo)} to (re)generate")

    if todo:
        client = _client()
        if client is None:
            print("     !! OPENAI_API_KEY not set — keeping cached notes, "
                  "regenerating none. The product still runs; notes may be stale.")
        else:
            for i, (key, payload, _row) in enumerate(todo, 1):
                note = _one_note(client, payload)
                cache[key] = {
                    "note": note,
                    "fingerprint": _fingerprint(payload),
                    "model": config.OPENAI_NOTES_MODEL,
                }
                print(f"     [{i}/{len(todo)}] {key}")
            write_json(CACHE_PATH, cache)

    stale = 0
    for key, payload, row in jobs:
        entry = cache.get(key)
        if not entry:
            continue
        row["analyst_note"] = {
            "text": entry["note"],
            "model": entry.get("model", config.OPENAI_NOTES_MODEL),
            "stale": entry.get("fingerprint") != _fingerprint(payload),
        }
        stale += int(row["analyst_note"]["stale"])
    if stale:
        print(f"     !! {stale} notes are stale (payload changed since generation)")

    write_json(CACHE_PATH, cache)
    return cache


def _client():
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    from openai import OpenAI

    return OpenAI(api_key=key)


def _one_note(client, payload: str) -> str:
    resp = client.chat.completions.create(
        model=config.OPENAI_NOTES_MODEL,
        temperature=0.2,  # low: we want the same argument every time, not variety
        messages=[
            {"role": "system", "content": NOTES_SYSTEM.format(max_words=config.NOTES_MAX_WORDS)},
            {"role": "user", "content": payload},
        ],
    )
    return resp.choices[0].message.content.strip()


if __name__ == "__main__":
    branches = read_json(config.DATA_PROCESSED / "branches.json", default=[])
    zones = [
        f["properties"]
        for f in (read_json(config.DATA_PROCESSED / "whitespace.geojson", default={}) or {}).get(
            "features", []
        )
    ]
    generate_notes(branches, zones)
    write_json(config.DATA_PROCESSED / "branches.json", branches)
    print("notes written back into branches.json")
    print(json.dumps(branches[0].get("analyst_note"), indent=2))
