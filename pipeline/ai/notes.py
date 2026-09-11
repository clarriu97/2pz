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
import os

from pipeline import config
from pipeline.ai.prompts import BRANCH_USER, NOTES_SYSTEM, ZONE_USER
from pipeline.models import AnalystNote, BranchRecord, Contribution, ZoneRecord
from pipeline.util import read_json, write_json

CACHE_PATH = config.DATA_PROCESSED / "analyst_notes.json"

# Notes are only worth generating where a human would actually read one. 23
# branches, plus every zone that is not a foregone SKIP.
ZONE_LABELS_WORTH_A_NOTE = {"GROW", "WATCH"}


def _fingerprint(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _contribution_lines(contributions: list[Contribution]) -> str:
    """Render a contribution breakdown as the model sees it: signed and ordered.

    Ordered by absolute impact so the largest driver is the first thing the
    model reads, which is what we want it to lead the note with.
    """
    rows = sorted(contributions, key=lambda c: -abs(c.contribution))
    return "\n".join(
        f"  - {c.label}: {c.raw_display} -> normalised {c.normalised:.2f} "
        f"x weight {c.weight:+.2f} = {c.contribution:+.3f}"
        for c in rows
    )


def branch_payload(row: BranchRecord) -> str:
    """The only thing the model is told about a branch: its scored record."""
    siblings = row.cannibalisation.siblings[:3]
    sibling_lines = (
        "\n".join(
            f"  - {s.name} at {s.distance_m / 1000:.1f} km covers "
            f"{s.share_of_my_catchment:.0%} of this catchment"
            for s in siblings
        )
        or "  - none"
    )
    caveat_lines = "\n".join(f"  - {c}" for c in row.confidence.caveats) or "  - none"
    return BRANCH_USER.format(
        name=row.name,
        area=row.area,
        emirate=row.emirate,
        recommendation=row.recommendation,
        decision_rule=row.decision_rule,
        strength_score=row.strength.score,
        strength_lines=_contribution_lines(row.strength.contributions),
        market_score=row.market.score,
        market_lines=_contribution_lines(row.market.contributions),
        radius_m=row.catchment_radius_m,
        urban_context=row.urban_context,
        catchment_area_km2=row.catchment_area_km2,
        competitor_count=row.competition.competitor_count,
        competitor_mean_rating=row.competition.competitor_mean_rating,
        overlapped_share=row.cannibalisation.overlapped_share,
        sibling_count=row.cannibalisation.sibling_count,
        sibling_lines=sibling_lines,
        confidence_level=row.confidence.level,
        caveat_lines=caveat_lines,
    )


def zone_payload(row: ZoneRecord, branch_names: dict[str, str]) -> str:
    return ZONE_USER.format(
        zone_id=row.zone_id,
        metro=row.metro,
        recommendation=row.recommendation,
        decision_rule=row.decision_rule,
        score=row.opportunity.score,
        lines=_contribution_lines(row.opportunity.contributions),
        area_km2=row.area_km2,
        residential_count=row.residential_count,
        activity_count=row.activity_count,
        affluence_count=row.affluence_count,
        nearest_branch_name=branch_names.get(row.nearest_branch_id, row.nearest_branch_id),
        distance_km=row.nearest_branch_distance_m / 1000,
        covered="inside its catchment" if row.inside_own_catchment else "beyond its catchment",
    )


def _jobs(
    branch_rows: list[BranchRecord], zone_rows: list[ZoneRecord]
) -> list[tuple[str, str, BranchRecord | ZoneRecord]]:
    """Every record worth a note, paired with the payload the model would see."""
    branch_names = {r.branch_id: r.name for r in branch_rows}
    jobs: list[tuple[str, str, BranchRecord | ZoneRecord]] = [
        (f"branch:{row.branch_id}", branch_payload(row), row) for row in branch_rows
    ]
    jobs += [
        (f"zone:{row.zone_id}", zone_payload(row, branch_names), row)
        for row in zone_rows
        if row.recommendation in ZONE_LABELS_WORTH_A_NOTE
    ]
    return jobs


def attach_notes(branch_rows: list[BranchRecord], zone_rows: list[ZoneRecord]) -> int:
    """Attach the committed notes to every row. No network, no key, no cost.

    This runs on EVERY build, not only when regenerating. The notes are part of
    the committed dataset — that is the whole point of pre-generating them — so
    a plain `pipeline.run` has to reproduce them, or the committed output and a
    fresh build would disagree, which is exactly what CI checks.

    Returns the number of stale notes: present in the cache, but generated from
    a payload that has since changed. Those are surfaced in the UI as stale
    rather than passed off as current.
    """
    cache: dict = read_json(CACHE_PATH, default={}) or {}
    stale = 0
    attached = 0

    for key, payload, row in _jobs(branch_rows, zone_rows):
        entry = cache.get(key)
        if not entry:
            continue
        row.analyst_note = AnalystNote(
            text=entry["note"],
            model=entry.get("model", config.OPENAI_NOTES_MODEL),
            stale=entry.get("fingerprint") != _fingerprint(payload),
        )
        attached += 1
        stale += int(row.analyst_note.stale)

    suffix = f", {stale} STALE (payload changed since generation)" if stale else ""
    print(f"     {attached} committed notes attached{suffix}")
    return stale


def generate_notes(branch_rows: list[BranchRecord], zone_rows: list[ZoneRecord]) -> dict[str, dict]:
    """Regenerate missing and stale notes, then attach them all.

    Only reached with --notes. Anything already cached whose payload still
    matches is left alone, so a re-run costs nothing.
    """
    cache: dict = read_json(CACHE_PATH, default={}) or {}
    jobs = _jobs(branch_rows, zone_rows)

    todo = [(k, p, r) for k, p, r in jobs if cache.get(k, {}).get("fingerprint") != _fingerprint(p)]
    print(f"     {len(jobs)} notes total, {len(todo)} to (re)generate")

    client = _client() if todo else None
    if todo and client is None:
        print(
            "     !! OPENAI_API_KEY not set — keeping cached notes, regenerating none. "
            "The product still runs; notes may be stale."
        )

    for i, (key, payload, _row) in enumerate(todo, 1):
        if client is None:
            break
        cache[key] = {
            "note": _one_note(client, payload),
            "fingerprint": _fingerprint(payload),
            "model": config.OPENAI_NOTES_MODEL,
        }
        # Written every iteration on purpose: a hundred sequential API calls
        # is long enough that an interruption part-way through should not
        # throw away the tokens already paid for.
        write_json(CACHE_PATH, cache)
        if i % 10 == 0 or i == len(todo):
            print(f"     [{i}/{len(todo)}] generated")

    attach_notes(branch_rows, zone_rows)
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


if __name__ == "__main__":  # pragma: no cover
    # Regenerate notes against the committed dataset without re-running the
    # whole geo pipeline.
    from pipeline.run import build

    build(with_notes=True)
