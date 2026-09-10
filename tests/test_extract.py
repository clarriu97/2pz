"""Bulk OSM sourcing from a local extract.

The fixtures below are tiny `.osm` XML files rather than `.pbf`, because
pyosmium reads both and hand-written XML is reviewable. That keeps the tests
free of the 250 MB download while still exercising the real reader.
"""

from __future__ import annotations

from typing import ClassVar

import httpx
import pytest

from pipeline.sourcing import extract as extract_mod
from pipeline.sourcing.demand import classify

DUBAI = (24.85, 55.05, 25.45, 55.60)

# Two nodes and one way inside Dubai, one node far outside it, and one
# untagged node that exists only to give the way a location.
OSM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="test">
  <node id="1" lat="25.20" lon="55.27" version="1">
    <tag k="amenity" v="cafe"/>
    <tag k="name" v="In Dubai"/>
  </node>
  <node id="2" lat="25.21" lon="55.28" version="1">
    <tag k="tourism" v="hotel"/>
  </node>
  <node id="3" lat="21.50" lon="39.20" version="1">
    <tag k="amenity" v="cafe"/>
    <tag k="name" v="Jeddah, outside every bbox"/>
  </node>
  <node id="10" lat="25.22" lon="55.29" version="1"/>
  <node id="11" lat="25.22" lon="55.30" version="1"/>
  <node id="12" lat="25.23" lon="55.31" version="1"/>
  <way id="100" version="1">
    <nd ref="10"/>
    <nd ref="11"/>
    <nd ref="12"/>
    <nd ref="10"/>
    <tag k="building" v="apartments"/>
  </way>
  <way id="101" version="1">
    <nd ref="10"/>
    <nd ref="11"/>
    <tag k="landuse" v="residential"/>
  </way>
  <way id="102" version="1">
    <tag k="building" v="apartments"/>
  </way>
  <node id="20" lat="25.24" lon="55.32" version="1">
    <tag k="highway" v="bus_stop"/>
  </node>
</osm>
"""


@pytest.fixture
def osm_file(tmp_path):
    path = tmp_path / "sample.osm"
    path.write_text(OSM_XML, encoding="utf-8")
    return path


class TestInAnyBbox:
    def test_inside(self) -> None:
        assert extract_mod.in_any_bbox(25.2, 55.27, [DUBAI])

    def test_outside(self) -> None:
        assert not extract_mod.in_any_bbox(21.5, 39.2, [DUBAI])

    def test_on_the_boundary_counts_as_inside(self) -> None:
        assert extract_mod.in_any_bbox(24.85, 55.05, [DUBAI])

    def test_matches_any_of_several_boxes(self) -> None:
        abu_dhabi = (24.29, 54.30, 24.60, 54.80)
        assert extract_mod.in_any_bbox(24.45, 54.40, [DUBAI, abu_dhabi])

    def test_no_boxes_matches_nothing(self) -> None:
        assert not extract_mod.in_any_bbox(25.2, 55.27, [])


class TestStreamFeatures:
    def test_keeps_tagged_nodes_inside_the_bbox(self, osm_file) -> None:
        found = extract_mod.stream_features(osm_file, [DUBAI], classify)
        assert ("activity", 25.20, 55.27) in found
        assert ("affluence", 25.21, 55.28) in found

    def test_discards_features_outside_every_bbox(self, osm_file) -> None:
        # The extract covers the whole GCC; everything outside our metros has
        # to be dropped or the demand normalisation is meaningless.
        found = extract_mod.stream_features(osm_file, [DUBAI], classify)
        assert all(lat > 24 for _c, lat, _lon in found)
        assert not any(round(lat, 2) == 21.50 for _c, lat, _lon in found)

    def test_places_ways_via_their_first_node(self, osm_file) -> None:
        """Residential buildings and land use are ways.

        They carry 40% of the demand weight, so a reader that only handled
        nodes would silently lose most of the signal.
        """
        found = extract_mod.stream_features(osm_file, [DUBAI], classify)
        residential = [f for f in found if f[0] == "residential"]
        assert len(residential) == 2  # the apartments way and the landuse way
        assert all((lat, lon) == (25.22, 55.29) for _c, lat, lon in residential)

    def test_two_ways_sharing_a_first_node_are_both_kept(self, osm_file) -> None:
        # Adjacent buildings share corner nodes. Keying the lookup by node
        # alone would keep one way and silently drop the other.
        found = extract_mod.stream_features(osm_file, [DUBAI], classify)
        assert sum(1 for c, _lat, _lon in found if c == "residential") == 2

    def test_ignores_a_way_with_no_nodes(self, osm_file) -> None:
        # Way 102 is tagged but has no node references; it must not crash or
        # be placed at a default coordinate.
        found = extract_mod.stream_features(osm_file, [DUBAI], classify)
        assert len(found) == 4

    def test_ignores_features_no_component_claims(self, osm_file) -> None:
        found = extract_mod.stream_features(osm_file, [DUBAI], classify)
        assert all(c in ("residential", "activity", "affluence") for c, _lat, _lon in found)

    def test_an_empty_bbox_list_yields_nothing(self, osm_file) -> None:
        assert extract_mod.stream_features(osm_file, [], classify) == []


class TestEnsureExtract:
    def test_an_existing_file_is_not_re_downloaded(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "extract.osm.pbf"
        target.write_bytes(b"x" * 2_000_000)

        def explode(*_a, **_k):  # pragma: no cover - must never run
            raise AssertionError("a present extract must not be re-downloaded")

        monkeypatch.setattr(httpx, "stream", explode)
        assert extract_mod.ensure_extract(path=target) == target

    def test_a_truncated_file_is_re_downloaded(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A few bytes on disk is an interrupted download, not an extract.
        target = tmp_path / "extract.osm.pbf"
        target.write_bytes(b"partial")
        _stub_download(monkeypatch, b"y" * 2_000_000)
        result = extract_mod.ensure_extract(path=target)
        assert result.read_bytes()[:1] == b"y"

    def test_downloads_to_a_partial_name_and_moves_on_success(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An interrupted download must not look like a finished one.

        Writing straight to the final path would leave a half-file that the
        size check above might accept on the next run.
        """
        target = tmp_path / "extract.osm.pbf"
        _stub_download(monkeypatch, b"z" * 2_000_000)
        extract_mod.ensure_extract(path=target)
        assert target.exists()
        assert not target.with_suffix(".partial").exists()

    def test_a_failed_download_leaves_no_final_file(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "extract.osm.pbf"

        class Response:
            headers: ClassVar[dict[str, str]] = {"content-length": "100"}

            @staticmethod
            def raise_for_status():
                raise httpx.HTTPStatusError("503", request=None, response=None)  # type: ignore[arg-type]

        class Stream:
            def __enter__(self):
                return Response()

            def __exit__(self, *_a):
                return False

        monkeypatch.setattr(httpx, "stream", lambda *_a, **_k: Stream())
        with pytest.raises(httpx.HTTPStatusError):
            extract_mod.ensure_extract(path=target)
        assert not target.exists()


def _stub_download(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> None:
    class Response:
        headers: ClassVar[dict[str, str]] = {"content-length": str(len(payload))}

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def iter_bytes(chunk_size: int = 1 << 20):
            for i in range(0, len(payload), chunk_size):
                yield payload[i : i + chunk_size]

    class Stream:
        def __enter__(self):
            return Response()

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(httpx, "stream", lambda *_a, **_k: Stream())
