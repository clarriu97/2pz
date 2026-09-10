"""End-to-end pipeline run with the network stubbed out.

This is the test that would catch a broken deliverable: it drives
`pipeline.run.build` through every stage — sourcing, geocoding, Overpass,
geometry, scoring, note generation and file writing — into a temporary data
directory, and then validates the files a reviewer would actually open.

Nothing here touches the internet. Nominatim and Overpass are replaced with
deterministic stubs, so the test asserts our behaviour rather than OSM's
current contents.
"""

from __future__ import annotations

import json

import pytest

from pipeline import config
from pipeline.ai import notes as notes_mod
from pipeline.models import BranchRecord, ModelCard
from pipeline.run import build, main
from pipeline.sourcing import branches as branches_mod
from pipeline.sourcing import competitors as competitors_mod
from pipeline.sourcing import demand as demand_mod
from pipeline.sourcing import extract as extract_mod
from pipeline.sourcing import osm as osm_mod

# A three-branch seed spanning two clusters, so the run exercises both the
# multi-cluster Overpass path and the self-overlap geometry.
SEED_CSV = """branch_id,name,area,emirate,address,google_rating,google_reviews
BD01,Bedashing Alpha,Mirdif,Dubai,"Mirdif, Dubai",4.7,600
BD02,Bedashing Beta,Al Warqa,Dubai,"Al Warqa, Dubai",4.5,150
BD03,Bedashing Gamma,Al Ain,Abu Dhabi,"Al Ain, Abu Dhabi",4.8,800
"""

GEOCODES = {
    "Mirdif": (25.2218, 55.4231),
    "Al Warqa": (25.1890, 55.4308),
    "Al Ain": (24.2249, 55.7452),
}


def _fake_osm_elements(bbox: tuple[float, float, float, float]) -> list[dict]:
    """A handful of plausible OSM features spread across the requested bbox."""
    south, west, north, east = bbox
    mid_lat = (south + north) / 2
    mid_lon = (west + east) / 2
    tag_sets = [
        {"shop": "beauty", "name": "Rival Beauty"},
        {"shop": "hairdresser", "name": "Corner Barber"},
        {"leisure": "spa", "name": "Palm Spa"},
        {"building": "apartments"},
        {"landuse": "residential"},
        {"amenity": "cafe", "name": "Cafe One"},
        {"shop": "supermarket", "name": "Mart"},
        {"tourism": "hotel", "name": "Grand Hotel"},
        {"shop": "mall", "name": "Big Mall"},
        {"leisure": "fitness_centre", "name": "Gym"},
    ]
    elements = []
    for i, tags in enumerate(tag_sets):
        # Deterministic ids derived from the bbox, so two different bboxes
        # produce different features and the dedupe logic is exercised.
        oid = abs(hash((round(mid_lat, 3), round(mid_lon, 3), i))) % 10**9
        elements.append(
            {
                "type": "node",
                "id": oid,
                "lat": round(mid_lat + (i - 5) * 0.004, 6),
                "lon": round(mid_lon + (i - 5) * 0.004, 6),
                "tags": tags,
            }
        )
    return elements


@pytest.fixture
def isolated_pipeline(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Redirect every path the pipeline writes to, and stub the network."""
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    web = tmp_path / "web"
    raw.mkdir(parents=True)

    monkeypatch.setattr(config, "DATA_RAW", raw)
    monkeypatch.setattr(config, "DATA_PROCESSED", processed)
    monkeypatch.setattr(config, "WEB_PUBLIC_DATA", web)

    seed = raw / "branches_seed.csv"
    seed.write_text(SEED_CSV, encoding="utf-8")
    monkeypatch.setattr(branches_mod, "SEED_CSV", seed)
    monkeypatch.setattr(branches_mod, "BRANCHES_RAW", raw / "branches_resolved.json")
    monkeypatch.setattr(branches_mod, "COORD_OVERRIDES", raw / "overrides.json")
    monkeypatch.setattr(competitors_mod, "COMPETITORS_RAW", raw / "competitors.json")
    monkeypatch.setattr(demand_mod, "DEMAND_RAW", raw / "activity.json")
    monkeypatch.setattr(notes_mod, "CACHE_PATH", processed / "analyst_notes.json")
    monkeypatch.setattr(osm_mod, "CACHE_DIR", raw / "osm")

    # Geocoding: resolve on the "<area>, <emirate>, UAE" candidate, which is
    # the branch the real pipeline usually takes.
    def geocode(candidates: list[str]):
        for candidate in candidates:
            for area, (lat, lon) in GEOCODES.items():
                if candidate.startswith(f"{area},"):
                    return lat, lon, candidate
        return None

    monkeypatch.setattr(branches_mod, "geocode_candidates", geocode)

    # Overpass: parse the bbox back out of the query and answer from the stub.
    def overpass(query: str, *, label: str, refresh: bool = False) -> list[dict]:
        import re

        first = re.search(r"\(([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+)\)", query)
        assert first, f"no bbox found in query for {label}"
        bbox = tuple(float(g) for g in first.groups())
        return _fake_osm_elements(bbox)  # type: ignore[arg-type]

    monkeypatch.setattr(competitors_mod, "overpass", overpass)

    # The demand layer streams a local OSM extract. Stub the download away and
    # answer from the same synthetic feature set, so the test exercises our
    # aggregation rather than a 250 MB file.
    monkeypatch.setattr(demand_mod, "ensure_extract", lambda: raw / "fake.osm.pbf")

    def stream(_path, bboxes, classify):
        out = []
        for bbox in bboxes:
            for el in _fake_osm_elements(bbox):
                component = classify(el["tags"])
                if component is not None:
                    out.append((component, el["lat"], el["lon"]))
        return out

    monkeypatch.setattr(demand_mod, "stream_features", stream)

    return {"raw": raw, "processed": processed, "web": web}


class TestFullBuild:
    def test_writes_every_file_the_product_reads(self, isolated_pipeline) -> None:
        build(refresh=True)
        processed = isolated_pipeline["processed"]
        for name in (
            "branches.json",
            "catchments.geojson",
            "overlaps.geojson",
            "competitors.geojson",
            "whitespace.geojson",
            "model_card.json",
        ):
            assert (processed / name).exists(), f"{name} was not written"

    def test_mirrors_the_same_bytes_into_the_web_bundle(self, isolated_pipeline) -> None:
        # The app must never render a different dataset from the committed one.
        build(refresh=True)
        for path in isolated_pipeline["processed"].glob("*"):
            mirrored = isolated_pipeline["web"] / path.name
            assert mirrored.read_bytes() == path.read_bytes()

    def test_the_output_validates_against_the_models(self, isolated_pipeline) -> None:
        build(refresh=True)
        rows = json.loads((isolated_pipeline["processed"] / "branches.json").read_text())
        records = [BranchRecord.model_validate(r) for r in rows]
        assert len(records) == 3
        assert {r.branch_id for r in records} == {"BD01", "BD02", "BD03"}

    def test_geocoded_coordinates_reach_the_output(self, isolated_pipeline) -> None:
        build(refresh=True)
        rows = json.loads((isolated_pipeline["processed"] / "branches.json").read_text())
        by_id = {r["branch_id"]: r for r in rows}
        assert by_id["BD01"]["lat"] == pytest.approx(25.2218, abs=1e-4)
        # The stub resolves on the first (full-address) candidate, so the
        # precision recorded must be "address" rather than a coarser fallback.
        assert by_id["BD01"]["geocode_precision"] == "address"

    def test_the_two_dubai_branches_overlap_and_al_ain_does_not(self, isolated_pipeline) -> None:
        build(refresh=True)
        overlaps = json.loads((isolated_pipeline["processed"] / "overlaps.geojson").read_text())
        pairs = {f["properties"]["pair_id"] for f in overlaps["features"]}
        assert pairs == {"BD01~BD02"}

    def test_a_second_run_uses_the_cache_and_needs_no_network(
        self, isolated_pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The reviewer's default invocation.

        `uv run python -m pipeline.run` with no flags must reproduce the
        dataset from committed caches alone.
        """
        build(refresh=True)

        def explode(*_a, **_k):  # pragma: no cover - must never run
            raise AssertionError("a cached run must not hit the network")

        monkeypatch.setattr(competitors_mod, "overpass", explode)
        monkeypatch.setattr(demand_mod, "ensure_extract", explode)
        monkeypatch.setattr(demand_mod, "stream_features", explode)
        monkeypatch.setattr(branches_mod, "geocode_candidates", explode)

        result = build()
        assert result["branches"] == 3

    def test_the_dataset_is_byte_reproducible(self, isolated_pipeline) -> None:
        """Every synthetic field is a pure function of the seed and the id.

        If this failed, the numbers in a recorded demo would not match the
        numbers in the live one.
        """
        build(refresh=True)
        first = (isolated_pipeline["processed"] / "branches.json").read_bytes()
        build()
        assert (isolated_pipeline["processed"] / "branches.json").read_bytes() == first

    def test_the_model_card_describes_this_run(self, isolated_pipeline) -> None:
        build(refresh=True)
        card = ModelCard.model_validate(
            json.loads((isolated_pipeline["processed"] / "model_card.json").read_text())
        )
        assert card.counts.branches == 3
        assert card.counts.competitors > 0
        assert card.seed == config.RANDOM_SEED

    def test_competitors_are_derived_from_the_stubbed_osm_features(self, isolated_pipeline) -> None:
        build(refresh=True)
        fc = json.loads((isolated_pipeline["processed"] / "competitors.geojson").read_text())
        names = {f["properties"]["name"] for f in fc["features"]}
        assert {"Rival Beauty", "Corner Barber", "Palm Spa"} & names

    def test_demand_features_reach_the_whitespace_grid(self, isolated_pipeline) -> None:
        build(refresh=True)
        fc = json.loads((isolated_pipeline["processed"] / "whitespace.geojson").read_text())
        assert fc["features"], "no scored zones survived"
        assert any(
            f["properties"]["residential_count"] + f["properties"]["affluence_count"] > 0
            for f in fc["features"]
        )

    def test_a_branch_that_cannot_be_geocoded_is_skipped_not_guessed(
        self, isolated_pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A branch with no coordinate has no catchment and no meaning.

        Dropping it loudly is right; placing it at (0, 0) would put a lounge
        in the Gulf of Guinea and silently corrupt every distance.
        """
        monkeypatch.setattr(branches_mod, "geocode_candidates", lambda _c: None)
        (isolated_pipeline["raw"] / "branches_resolved.json").unlink(missing_ok=True)
        with pytest.raises(RuntimeError, match="No branches could be resolved"):
            build(refresh=True)

    def test_manual_overrides_win_over_the_geocoder(
        self, isolated_pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pipeline.util import write_json

        write_json(
            isolated_pipeline["raw"] / "overrides.json",
            {"BD03": {"lat": 24.2000, "lon": 55.7000, "precision": "manual"}},
        )
        build(refresh=True)
        rows = json.loads((isolated_pipeline["processed"] / "branches.json").read_text())
        gamma = next(r for r in rows if r["branch_id"] == "BD03")
        assert gamma["lat"] == pytest.approx(24.2000)
        assert gamma["geocode_precision"] == "manual"


class TestBuildWithNotes:
    def test_notes_are_generated_and_land_in_the_output(
        self, isolated_pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Client:
            class chat:
                class completions:
                    @staticmethod
                    def create(**_kwargs):
                        class Choice:
                            message = type("M", (), {"content": "Grounded note."})()

                        return type("R", (), {"choices": [Choice()]})()

        monkeypatch.setattr(notes_mod, "_client", lambda: Client())

        build(refresh=True, with_notes=True)
        rows = json.loads((isolated_pipeline["processed"] / "branches.json").read_text())
        assert all(r["analyst_note"]["text"] == "Grounded note." for r in rows)
        assert all(r["analyst_note"]["stale"] is False for r in rows)

    def test_without_a_key_the_build_still_succeeds(
        self, isolated_pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The fallback story, asserted rather than described.
        monkeypatch.setattr(notes_mod, "_client", lambda: None)
        build(refresh=True, with_notes=True)
        rows = json.loads((isolated_pipeline["processed"] / "branches.json").read_text())
        assert all(r["analyst_note"] is None for r in rows)


class TestCli:
    def test_the_default_invocation_builds_from_cache(
        self, isolated_pipeline, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        build(refresh=True)
        monkeypatch.setattr("sys.argv", ["pipeline.run"])
        main()
        assert "done: 3 branches" in capsys.readouterr().out

    def test_refresh_is_wired_to_the_flag(
        self, isolated_pipeline, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        monkeypatch.setattr("sys.argv", ["pipeline.run", "--refresh"])
        main()
        assert "done: 3 branches" in capsys.readouterr().out


class TestOfflineMode:
    """The guarantee CI relies on.

    Without an explicit offline mode, a missing committed cache would be
    silently fetched over the runner's network and the build would go green
    for the wrong reason — passing only because GitHub's machine had internet.
    """

    def test_a_cache_miss_fails_with_an_actionable_message(
        self, isolated_pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(osm_mod, "OFFLINE", False)
        # Restore the real clients so nothing can quietly succeed.
        monkeypatch.setattr(competitors_mod, "overpass", osm_mod.overpass)
        monkeypatch.setattr(demand_mod, "ensure_extract", extract_mod.ensure_extract)
        with pytest.raises(osm_mod.CacheMiss, match="--refresh"):
            build(offline=True)

    def test_offline_and_refresh_are_rejected_together(self, isolated_pipeline) -> None:
        with pytest.raises(ValueError, match="contradictory"):
            build(offline=True, refresh=True)

    def test_a_fully_cached_run_succeeds_offline(self, isolated_pipeline) -> None:
        build(refresh=True)
        # The stubs are still installed, but offline mode short-circuits before
        # them, so this only passes because every response was cached.
        assert build(offline=True)["branches"] == 3

    def test_offline_is_not_left_set_after_a_run(self, isolated_pipeline) -> None:
        # A leaked global would silently make later runs refuse to fetch.
        build(refresh=True)
        build(offline=True)
        assert osm_mod.OFFLINE is False

    def test_a_missing_geocode_fails_offline_rather_than_calling_nominatim(
        self, isolated_pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pipeline.sourcing import geocode as geocode_mod

        monkeypatch.setattr(branches_mod, "geocode_candidates", geocode_mod.geocode_candidates)
        monkeypatch.setattr(geocode_mod, "CACHE_PATH", isolated_pipeline["raw"] / "gc.json")
        monkeypatch.setattr(osm_mod, "OFFLINE", True)
        with pytest.raises(osm_mod.CacheMiss, match="No committed geocode"):
            build(offline=True)
