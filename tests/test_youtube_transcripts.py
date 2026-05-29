"""Tests for YouTube transcript acquisition + packet attachment (Stage A).

All deterministic and offline: transcript fetching is exercised through an
injected fake fetcher, so these tests never hit the network or require
youtube-transcript-api / yt-dlp to be installed.
"""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

from ingestion.espn_mystics import load_fixture_payload
from ingestion.fetchers.youtube_transcripts import (
    _correct_text,
    build_media_transcripts,
    correct_video_names,
    load_roster_name_tokens,
    make_name_corrector,
)
from ingestion.mystics_normalizer import build_postgame_packet, enrich_packet_with_transcripts
from newsroom.schemas import validate_normalized_game_packet

FIXTURE = Path("tests/fixtures/espn_mystics_postgame_401856918.json")
RETRIEVED = "2026-05-29T00:00:00Z"

MANUAL_OVERRIDE = [
    {"video_id": "yvVYc7CfIBo", "kind": "highlights"},
    {"video_id": "lZ1U_8wCp6g", "kind": "presser"},
]


def fake_fetcher(video_id, kind, *, languages=("en",), retrieved_at=None):
    """Stand-in for fetch_transcript — returns the raw (pre-correction) shape."""
    retrieved = retrieved_at or RETRIEVED
    source_url = f"https://www.youtube.com/watch?v={video_id}"
    if video_id == "BLOCKEDVID":
        return {
            "video_id": video_id,
            "kind": kind,
            "status": "missing",
            "reason": "RequestBlocked: datacenter/IP blocked",
            "source_url": source_url,
            "retrieved_at": retrieved,
        }
    segments = [
        {"start": 0.0, "duration": 1.5, "text": "Amore drives and Catron hits the three."},
        {"start": 1.5, "duration": 1.5, "text": "Great pass from Sonya to Austin."},
    ]
    text = " ".join(seg["text"] for seg in segments)
    return {
        "video_id": video_id,
        "kind": kind,
        "status": "ok",
        "track": "auto",
        "language": "en",
        "snippet_count": len(segments),
        "char_count": len(text),
        "segments": segments,
        "text": text,
        "source_url": source_url,
        "retrieved_at": retrieved,
    }


class NameCorrectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tokens = load_roster_name_tokens(("mystics",))

    def test_roster_tokens_loaded(self) -> None:
        for token in ("amoore", "citron", "sonia", "michaela", "florez", "austin"):
            self.assertIn(token, self.tokens)

    def test_corrects_real_misspellings(self) -> None:
        cases = {
            "Amore": "Amoore",
            "AMORE": "AMOORE",
            "Sonya": "Sonia",
            "Catron": "Citron",
            "Flores": "Florez",
        }
        for wrong, right in cases.items():
            corrected, corrections = _correct_text(wrong, self.tokens)
            self.assertEqual(corrected, right, f"{wrong!r} should correct to {right!r}")
            self.assertEqual(corrections, [(wrong, right)])

    def test_preserves_correct_possessive_and_words(self) -> None:
        # "Michaela's" is correct (just possessive) -> untouched.
        corrected, corrections = _correct_text("Michaela's night", self.tokens)
        self.assertEqual(corrected, "Michaela's night")
        self.assertEqual(corrections, [])
        # "more" must NOT become "amoore" (first-letter guard).
        corrected, corrections = _correct_text("one more possession", self.tokens)
        self.assertEqual(corrected, "one more possession")
        # An exact roster name is left alone.
        corrected, _ = _correct_text("Austin scored inside", self.tokens)
        self.assertEqual(corrected, "Austin scored inside")

    def test_roster_only_excludes_staff_collisions(self) -> None:
        # Coaching staff are excluded by default, so common words "turn"/"turned"
        # are not pulled toward assistant coach "Barbara Turner".
        self.assertNotIn("turner", self.tokens)
        corrected, corrections = _correct_text("They turn it over and turned around", self.tokens)
        self.assertEqual(corrected, "They turn it over and turned around")
        self.assertEqual(corrections, [])
        # include_staff=True opts back into coach-name matching.
        staff_tokens = load_roster_name_tokens(("mystics",), include_staff=True)
        self.assertIn("turner", staff_tokens)

    def test_make_name_corrector_closure(self) -> None:
        corrector = make_name_corrector(self.tokens)
        corrected, corrections = corrector("Amore for three")
        self.assertEqual(corrected, "Amoore for three")
        self.assertEqual(corrections, [("Amore", "Amoore")])


class CorrectVideoNamesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tokens = load_roster_name_tokens(("mystics",))

    def test_adds_corrected_fields_and_preserves_raw(self) -> None:
        video = fake_fetcher("vid1", "highlights")
        corrected = correct_video_names(video, self.tokens)
        # raw preserved
        self.assertIn("Amore", corrected["text"])
        self.assertEqual(corrected["segments"][0]["text"], "Amore drives and Catron hits the three.")
        # corrected variant
        self.assertIn("Amoore", corrected["corrected_text"])
        self.assertIn("Citron", corrected["corrected_text"])
        self.assertIn("Sonia", corrected["corrected_text"])
        pairs = {(c["from"], c["to"]) for c in corrected["name_corrections"]}
        self.assertIn(("Amore", "Amoore"), pairs)
        self.assertIn(("Catron", "Citron"), pairs)
        self.assertIn(("Sonya", "Sonia"), pairs)

    def test_missing_video_passes_through_uncorrected(self) -> None:
        video = fake_fetcher("BLOCKEDVID", "presser")
        out = correct_video_names(video, self.tokens)
        self.assertEqual(out["status"], "missing")
        self.assertNotIn("corrected_text", out)


class BuildMediaTranscriptsTests(unittest.TestCase):
    def test_build_with_injected_fetcher(self) -> None:
        media = build_media_transcripts(
            MANUAL_OVERRIDE, retrieved_at=RETRIEVED, fetcher=fake_fetcher
        )
        self.assertEqual(len(media), 2)
        self.assertEqual([m["kind"] for m in media], ["highlights", "presser"])
        for item in media:
            self.assertEqual(item["status"], "ok")
            self.assertEqual(item["track"], "auto")
            self.assertIn("corrected_text", item)
            self.assertIn("name_corrections", item)

    def test_accepts_tuple_inputs_and_missing(self) -> None:
        media = build_media_transcripts(
            [("vid1", "highlights"), ("BLOCKEDVID", "presser")],
            retrieved_at=RETRIEVED,
            fetcher=fake_fetcher,
        )
        self.assertEqual(media[0]["status"], "ok")
        self.assertEqual(media[1]["status"], "missing")
        self.assertIn("RequestBlocked", media[1]["reason"])


class PacketAttachmentTests(unittest.TestCase):
    def _base_packet(self) -> dict:
        return build_postgame_packet(load_fixture_payload(FIXTURE))

    def test_default_path_has_no_media_transcripts(self) -> None:
        packet = self._base_packet()
        self.assertNotIn("media_transcripts", packet)

    def test_enrich_attaches_block_sources_and_validates(self) -> None:
        packet = self._base_packet()
        source_count_before = len(packet["sources"])
        enriched = enrich_packet_with_transcripts(
            packet,
            transcript_videos=MANUAL_OVERRIDE,
            fetcher=fake_fetcher,
            retrieved_at=RETRIEVED,
        )
        self.assertEqual(enriched["schema_version"], "mystics-postgame-recap/v0.2")
        self.assertEqual(len(enriched["media_transcripts"]), 2)
        # one provenance source added per video
        self.assertEqual(len(enriched["sources"]), source_count_before + 2)
        youtube_sources = [s for s in enriched["sources"] if "YouTube" in s["name"]]
        self.assertEqual(len(youtube_sources), 2)
        # re-validates cleanly (enrich calls the validator)
        validate_normalized_game_packet(enriched)

    def test_build_postgame_packet_include_flag_attaches(self) -> None:
        packet = build_postgame_packet(
            load_fixture_payload(FIXTURE),
            include_transcripts=True,
            transcript_videos=MANUAL_OVERRIDE,
            transcript_fetcher=fake_fetcher,
        )
        self.assertEqual(len(packet["media_transcripts"]), 2)
        self.assertTrue(any("Amoore" in m["corrected_text"] for m in packet["media_transcripts"]))


class MediaTranscriptSchemaTests(unittest.TestCase):
    def _enriched(self) -> dict:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        return enrich_packet_with_transcripts(
            packet, transcript_videos=MANUAL_OVERRIDE, fetcher=fake_fetcher, retrieved_at=RETRIEVED
        )

    def test_missing_record_validates(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        enriched = enrich_packet_with_transcripts(
            packet,
            transcript_videos=[{"video_id": "BLOCKEDVID", "kind": "highlights"}],
            fetcher=fake_fetcher,
            retrieved_at=RETRIEVED,
        )
        self.assertEqual(enriched["media_transcripts"][0]["status"], "missing")
        validate_normalized_game_packet(enriched)

    def test_invalid_kind_rejected(self) -> None:
        packet = self._enriched()
        packet["media_transcripts"][0]["kind"] = "interview"
        with self.assertRaises(ValueError):
            validate_normalized_game_packet(packet)

    def test_ok_record_missing_corrected_text_rejected(self) -> None:
        packet = self._enriched()
        del packet["media_transcripts"][0]["corrected_text"]
        with self.assertRaises(ValueError):
            validate_normalized_game_packet(packet)

    def test_bad_segment_shape_rejected(self) -> None:
        packet = self._enriched()
        packet["media_transcripts"][0]["segments"] = [{"start": 0.0}]  # missing duration/text
        with self.assertRaises(ValueError):
            validate_normalized_game_packet(packet)


if __name__ == "__main__":
    unittest.main()
