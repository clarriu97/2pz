"""The AI layer's grounding.

The claim this product makes about its notes is that the model is handed the
scored record and nothing else, so every sentence it writes is traceable to a
number in the breakdown. These tests hold the prompt construction to that
claim, and check that a note whose payload has changed is surfaced as stale
rather than passed off as current.

No test calls OpenAI. The client is stubbed, because what is worth testing is
what we send and how we cache it, not what the model replies.
"""

from __future__ import annotations

import pytest

from pipeline import config
from pipeline.ai import notes as notes_mod
from pipeline.ai.prompts import CHAT_SYSTEM, NOTES_SYSTEM
from tests.helpers import make_branch_record, make_zone_record


class TestNotesPrompt:
    def test_forbids_inventing_facts(self) -> None:
        text = NOTES_SYSTEM.format(max_words=config.NOTES_MAX_WORDS)
        assert "Use ONLY the numbers you are given" in text
        assert "Never invent revenue" in text

    def test_forbids_overriding_the_label(self) -> None:
        # The model explains a decision; it must not quietly make a different
        # one, or the note and the map would contradict each other.
        text = NOTES_SYSTEM.format(max_words=config.NOTES_MAX_WORDS)
        assert "Never recommend something other than the label" in text

    def test_requires_flagging_simulated_signals(self) -> None:
        text = NOTES_SYSTEM.format(max_words=config.NOTES_MAX_WORDS)
        assert "simulated or low-confidence" in text

    def test_carries_the_configured_word_limit(self) -> None:
        text = NOTES_SYSTEM.format(max_words=config.NOTES_MAX_WORDS)
        assert str(config.NOTES_MAX_WORDS) in text


class TestChatPrompt:
    def test_forbids_answering_from_memory(self) -> None:
        assert "ALWAYS call a tool" in CHAT_SYSTEM
        assert "Never answer portfolio questions from memory" in CHAT_SYSTEM

    def test_names_the_simulated_signals(self) -> None:
        for term in ("simulated", "built-form proxy", "radii, not drive times"):
            assert term in CHAT_SYSTEM

    def test_requires_saying_what_is_missing_rather_than_guessing(self) -> None:
        assert "Do not guess" in CHAT_SYSTEM


class TestContributionLines:
    def test_orders_by_absolute_impact(self) -> None:
        record = make_branch_record()
        lines = notes_mod._contribution_lines(record.strength.contributions).splitlines()
        magnitudes = [abs(float(line.rsplit("=", 1)[1].strip())) for line in lines]
        assert magnitudes == sorted(magnitudes, reverse=True)

    def test_shows_the_arithmetic_not_just_the_result(self) -> None:
        # The model is asked to translate arithmetic into an argument, so it
        # has to be able to see the arithmetic.
        line = notes_mod._contribution_lines(make_branch_record().strength.contributions)
        assert "normalised" in line
        assert "x weight" in line


class TestBranchPayload:
    def test_states_the_label_and_the_rule_that_produced_it(self) -> None:
        record = make_branch_record(recommendation="SHRINK", rule="strength 0.30 < 0.42")
        payload = notes_mod.branch_payload(record)
        assert "Recommendation: SHRINK" in payload
        assert "strength 0.30 < 0.42" in payload

    def test_includes_both_axes_with_their_breakdowns(self) -> None:
        payload = notes_mod.branch_payload(make_branch_record())
        assert "Branch strength =" in payload
        assert "Market attractiveness & defensibility =" in payload
        assert "Guest rating" in payload

    def test_lists_siblings_when_there_is_self_overlap(self) -> None:
        payload = notes_mod.branch_payload(make_branch_record(overlap=0.6, siblings=2))
        assert "Sibling 0" in payload
        assert "of this catchment" in payload

    def test_says_none_when_there_is_no_overlap(self) -> None:
        payload = notes_mod.branch_payload(make_branch_record(overlap=0.0))
        assert "- none" in payload

    def test_passes_the_confidence_caveats_through(self) -> None:
        payload = notes_mod.branch_payload(
            make_branch_record(caveats=["Only 38 reviews, so the rating is thin."])
        )
        assert "Only 38 reviews" in payload

    def test_never_leaks_a_field_the_model_should_not_reason_from(self) -> None:
        """The payload is the whole of the model's world.

        Nothing about revenue, rent or staffing exists in this dataset, and the
        prompt forbids inventing it — so the payload must not contain a stray
        field that invites it.
        """
        payload = notes_mod.branch_payload(make_branch_record()).lower()
        for forbidden in ("revenue", "rent", "profit", "staff", "salary"):
            assert forbidden not in payload


class TestZonePayload:
    def test_resolves_the_nearest_branch_to_its_name(self) -> None:
        payload = notes_mod.zone_payload(make_zone_record(), {"BD01": "Bedashing Alpha"})
        assert "Bedashing Alpha" in payload

    def test_falls_back_to_the_id_when_the_name_is_unknown(self) -> None:
        payload = notes_mod.zone_payload(make_zone_record(), {})
        assert "BD01" in payload

    def test_states_whether_the_cell_is_already_covered(self) -> None:
        assert "beyond its catchment" in notes_mod.zone_payload(make_zone_record(inside=False), {})
        assert "inside its catchment" in notes_mod.zone_payload(make_zone_record(inside=True), {})

    def test_warns_the_model_that_demand_is_a_proxy(self) -> None:
        payload = notes_mod.zone_payload(make_zone_record(), {})
        assert "built-form proxy" in payload
        assert "not census" in payload


class TestFingerprintAndStaleness:
    def test_the_same_payload_fingerprints_identically(self) -> None:
        assert notes_mod._fingerprint("abc") == notes_mod._fingerprint("abc")

    def test_a_changed_payload_changes_the_fingerprint(self) -> None:
        assert notes_mod._fingerprint("abc") != notes_mod._fingerprint("abd")

    def test_a_matching_cache_entry_is_attached_as_fresh(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(notes_mod, "CACHE_PATH", tmp_path / "notes.json")
        record = make_branch_record()
        payload = notes_mod.branch_payload(record)

        from pipeline.util import write_json

        write_json(
            tmp_path / "notes.json",
            {
                f"branch:{record.branch_id}": {
                    "note": "A grounded note.",
                    "fingerprint": notes_mod._fingerprint(payload),
                    "model": "test-model",
                }
            },
        )
        monkeypatch.setattr(notes_mod, "_client", lambda: None)

        notes_mod.generate_notes([record], [])
        assert record.analyst_note is not None
        assert record.analyst_note.text == "A grounded note."
        assert record.analyst_note.stale is False

    def test_a_stale_note_is_surfaced_rather_than_hidden(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pre-generated notes go stale when the config changes.

        Showing a stale note as current would be the one place this product
        could quietly mislead, so the staleness travels with the note into the
        UI.
        """
        monkeypatch.setattr(notes_mod, "CACHE_PATH", tmp_path / "notes.json")
        record = make_branch_record()

        from pipeline.util import write_json

        write_json(
            tmp_path / "notes.json",
            {
                f"branch:{record.branch_id}": {
                    "note": "Written against an older model.",
                    "fingerprint": "0" * 16,
                    "model": "test-model",
                }
            },
        )
        monkeypatch.setattr(notes_mod, "_client", lambda: None)

        notes_mod.generate_notes([record], [])
        assert record.analyst_note is not None
        assert record.analyst_note.stale is True

    def test_without_a_key_nothing_is_generated_and_nothing_crashes(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The fallback story: the product runs with no OPENAI_API_KEY.
        monkeypatch.setattr(notes_mod, "CACHE_PATH", tmp_path / "notes.json")
        monkeypatch.setattr(notes_mod, "_client", lambda: None)
        record = make_branch_record()
        notes_mod.generate_notes([record], [])
        assert record.analyst_note is None

    def test_only_actionable_zones_are_given_notes(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A note per SKIP hex would be a thousand pointless API calls.

        Notes are generated where a human would actually read one.
        """
        monkeypatch.setattr(notes_mod, "CACHE_PATH", tmp_path / "notes.json")
        calls: list[str] = []

        class Client:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        calls.append(kwargs["messages"][1]["content"])

                        class Choice:
                            message = type("M", (), {"content": "note text"})()

                        return type("R", (), {"choices": [Choice()]})()

        monkeypatch.setattr(notes_mod, "_client", lambda: Client())

        zones = [
            make_zone_record(zone_id="871e1d0ffffffff", recommendation="GROW"),
            make_zone_record(zone_id="871e1d1ffffffff", recommendation="WATCH"),
            make_zone_record(zone_id="871e1d2ffffffff", recommendation="SKIP"),
        ]
        notes_mod.generate_notes([], zones)
        assert len(calls) == 2
        assert zones[2].analyst_note is None

    def test_generation_writes_a_reusable_cache(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(notes_mod, "CACHE_PATH", tmp_path / "notes.json")
        created = {"count": 0}

        class Client:
            class chat:
                class completions:
                    @staticmethod
                    def create(**_kwargs):
                        created["count"] += 1

                        class Choice:
                            message = type("M", (), {"content": "  note text  "})()

                        return type("R", (), {"choices": [Choice()]})()

        monkeypatch.setattr(notes_mod, "_client", lambda: Client())

        record = make_branch_record()
        notes_mod.generate_notes([record], [])
        assert created["count"] == 1
        assert record.analyst_note is not None
        assert record.analyst_note.text == "note text"  # stripped

        # A second run over an unchanged record must not re-spend the tokens.
        second = make_branch_record()
        notes_mod.generate_notes([second], [])
        assert created["count"] == 1
        assert second.analyst_note is not None
        assert second.analyst_note.stale is False


class TestClient:
    def test_returns_none_without_a_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert notes_mod._client() is None

    def test_builds_a_client_when_a_key_is_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
        assert notes_mod._client() is not None
