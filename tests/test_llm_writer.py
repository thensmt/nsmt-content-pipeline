"""Tests for the Mystics LLM writer + the verifiable-quote guardrail (Stage B).

All offline: the Anthropic HTTP call is injected via a fake ``transport`` and the
quote guardrail is pure/deterministic, so no network or API key is needed.

The two safety tests that matter most:
  - test_real_presser_quote_passes
  - test_fabricated_quote_hard_fails  (and test_altered_quote_hard_fails)
"""

from __future__ import annotations

import unittest
from pathlib import Path

import ingestion.mystics_postgame_recap as recap_cli
from ingestion.espn_mystics import load_fixture_payload
from ingestion.mystics_normalizer import build_postgame_packet, enrich_packet_with_transcripts
from newsroom import llm_writer
from newsroom.claim_audit import format_claim_evidence_audit, validate_person_names, verify_quotes
from newsroom.llm_writer import _build_payload, _parse_output, build_system_prefix, write_recap
from newsroom.qa import format_editorial_qa_report

FIXTURE = Path("tests/fixtures/espn_mystics_postgame_401856918.json")

PRESSER_LINES = [
    "We just didn't take care of the ball tonight.",
    "Amoore set the tone early and we followed her lead.",
    "Give Seattle credit, they made us uncomfortable on every possession.",
]
HIGHLIGHT_LINES = [
    "Storm and Mystics getting set here in Seattle.",
    "And Citron pulls up from deep, good.",
]


def _fake_fetch(video_id, kind, *, languages=("en",), retrieved_at=None):
    lines = PRESSER_LINES if kind == "presser" else HIGHLIGHT_LINES
    segments = [{"start": float(i * 3), "duration": 3.0, "text": line} for i, line in enumerate(lines)]
    text = " ".join(line for line in lines)
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
        "source_url": f"https://www.youtube.com/watch?v={video_id}",
        "retrieved_at": retrieved_at or "2026-05-29T00:00:00Z",
    }


def _enriched_packet():
    packet = build_postgame_packet(load_fixture_payload(FIXTURE))
    return enrich_packet_with_transcripts(
        packet,
        transcript_videos=[{"video_id": "PRES1", "kind": "presser"}, {"video_id": "HILITE1", "kind": "highlights"}],
        fetcher=_fake_fetch,
        retrieved_at="2026-05-29T00:00:00Z",
    )


def _llm_response(body_text, *, headline="Mystics drop one in Seattle", excerpt="Washington could not solve the Storm."):
    output = f"HEADLINE: {headline}\n\n{body_text}\n\nEXCERPT: {excerpt}"
    return {
        "content": [{"type": "text", "text": output}],
        "usage": {
            "input_tokens": 1200,
            "output_tokens": 480,
            "cache_creation_input_tokens": 3100,
            "cache_read_input_tokens": 0,
        },
    }


class QuoteGuardrailTests(unittest.TestCase):
    def setUp(self):
        self.packet = _enriched_packet()

    def test_real_presser_quote_passes(self):
        body = (
            'Washington never found its footing in Seattle. Afterward, Georgia Amoore '
            'was direct: "We just didn\'t take care of the ball tonight." The turnovers told the story.'
        )
        result = verify_quotes(body, self.packet)
        self.assertFalse(result["hard_fail"])
        self.assertEqual(result["verified_count"], 1)
        self.assertTrue(result["quotes"][0]["verified"])
        self.assertGreaterEqual(result["quotes"][0]["match_ratio"], 0.9)
        self.assertTrue(result["used_segments"])

    def test_fabricated_quote_hard_fails(self):
        # The safety test that matters most: a quote that is NOT in the transcript.
        body = 'Amoore said, "We executed the game plan to perfection and dominated every quarter."'
        result = verify_quotes(body, self.packet)
        self.assertTrue(result["hard_fail"])
        self.assertEqual(result["verified_count"], 0)
        self.assertEqual(result["unverified_count"], 1)
        self.assertLess(result["quotes"][0]["match_ratio"], 0.9)

    def test_altered_quote_hard_fails(self):
        # Paraphrasing a real quote into quotation marks must also be caught.
        body = 'Amoore said, "We just didn\'t take care of the basketball this evening."'
        result = verify_quotes(body, self.packet)
        self.assertTrue(result["hard_fail"])

    def test_attributed_quote_flagged_for_review(self):
        body = 'Kiki Iriafen said, "Give Seattle credit, they made us uncomfortable on every possession."'
        result = verify_quotes(body, self.packet)
        self.assertFalse(result["hard_fail"])
        self.assertTrue(result["requires_external_review"])
        self.assertEqual(result["attributed_quotes"][0]["speaker"], "Kiki Iriafen")

    def test_unattributed_verified_quote_not_flagged(self):
        body = 'The message in the room was blunt: "We just didn\'t take care of the ball tonight."'
        result = verify_quotes(body, self.packet)
        self.assertFalse(result["hard_fail"])
        self.assertFalse(result["requires_external_review"])

    def test_no_transcripts_no_quotes_no_failure(self):
        plain = build_postgame_packet(load_fixture_payload(FIXTURE))
        result = verify_quotes("A clean recap with no quotation marks at all.", plain)
        self.assertEqual(result["checked"], 0)
        self.assertFalse(result["hard_fail"])


class LLMWriterTests(unittest.TestCase):
    def setUp(self):
        self.packet = _enriched_packet()

    def test_write_recap_parses_and_verifies(self):
        body = (
            'Seattle controlled the glass and the Mystics paid for it. "We just didn\'t take care '
            'of the ball tonight," Georgia Amoore said, and the box score agreed.'
        )

        def transport(payload, api_key):
            return _llm_response(body)

        result = write_recap(self.packet, writer_profile=self.packet["writer_profile"], transport=transport)
        self.assertEqual(result["headline"], "Mystics drop one in Seattle")
        self.assertIn("Seattle controlled the glass", result["body"])
        self.assertTrue(result["excerpt"])
        self.assertFalse(result["quote_verification"]["hard_fail"])
        self.assertTrue(result["used_segments"])
        self.assertEqual(result["usage"]["cache_creation_input_tokens"], 3100)

    def test_payload_has_cache_breakpoints(self):
        payload = _build_payload(self.packet, self.packet["writer_profile"])
        self.assertEqual(payload["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(payload["messages"][0]["content"][0]["cache_control"], {"type": "ephemeral"})
        # the dynamic facts block is NOT cached
        self.assertNotIn("cache_control", payload["messages"][0]["content"][1])
        # web_search is disabled for the Mystics writer (MAX_WEB_SEARCHES = 0)
        self.assertNotIn("tools", payload)
        self.assertEqual(payload["model"], "claude-sonnet-4-6")

    def test_system_prefix_carries_house_and_transcript_rules(self):
        prefix = build_system_prefix(self.packet["writer_profile"])
        self.assertIn("No em dashes", prefix)
        self.assertIn("NEVER quote an announcer", prefix)
        self.assertIn("verbatim", prefix)
        self.assertIn("Maya Brooks", prefix)

    def test_parse_output_fallback_without_markers(self):
        headline, body, excerpt = _parse_output("Just a headline line\n\nThen the body paragraph.")
        self.assertEqual(headline, "Just a headline line")
        self.assertIn("body paragraph", body)
        self.assertEqual(excerpt, "")

    def test_missing_api_key_raises(self):
        with self.assertRaises(RuntimeError):
            write_recap(self.packet, writer_profile=self.packet["writer_profile"], api_key=None)


class OrchestratorFallbackTests(unittest.TestCase):
    """_resolve_article_markdown: LLM when clean, deterministic on hard-fail/error."""

    def setUp(self):
        self.packet = _enriched_packet()
        self._orig = llm_writer.write_recap

    def tearDown(self):
        llm_writer.write_recap = self._orig

    def test_clean_llm_used(self):
        def fake_write_recap(packet, *, writer_profile=None, **kwargs):
            body = '"We just didn\'t take care of the ball tonight," Amoore said after the loss.'
            return {
                "headline": "Mystics fall to Storm",
                "body": "Washington lost the possession battle in Seattle. " + body,
                "excerpt": "Turnovers sank the Mystics.",
                "used_segments": [{"video_id": "PRES1"}],
                "quote_verification": verify_quotes("Washington lost the possession battle in Seattle. " + body, self.packet),
                "model": "claude-sonnet-4-6",
                "usage": {"input_tokens": 10},
            }

        llm_writer.write_recap = fake_write_recap
        markdown, meta = recap_cli._resolve_article_markdown(self.packet, llm_mode=True)
        self.assertTrue(meta["llm_used"])
        self.assertIn("Mystics fall to Storm", markdown)
        self.assertIn("**Excerpt:**", markdown)
        self.assertIn("**By Maya Brooks", markdown)

    def test_hard_fail_falls_back_to_deterministic(self):
        def fake_write_recap(packet, *, writer_profile=None, **kwargs):
            body = 'Amoore said, "We dominated from start to finish and never trailed."'
            return {
                "headline": "Bogus",
                "body": body,
                "excerpt": "x",
                "used_segments": [],
                "quote_verification": verify_quotes(body, self.packet),
                "model": "claude-sonnet-4-6",
                "usage": {},
            }

        llm_writer.write_recap = fake_write_recap
        markdown, meta = recap_cli._resolve_article_markdown(self.packet, llm_mode=True)
        self.assertFalse(meta["llm_used"])
        self.assertEqual(meta["reason"], "quote_hard_fail")
        self.assertNotIn("dominated from start to finish", markdown)  # deterministic fallback used

    def test_api_error_falls_back_to_deterministic(self):
        def boom(packet, *, writer_profile=None, **kwargs):
            raise RuntimeError("ANTHROPIC_API_KEY not set; cannot run the LLM writer")

        llm_writer.write_recap = boom
        markdown, meta = recap_cli._resolve_article_markdown(self.packet, llm_mode=True)
        self.assertFalse(meta["llm_used"])
        self.assertTrue(meta["reason"].startswith("llm_error"))
        self.assertIn("# ", markdown)  # deterministic document rendered


class AuditAndQAIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.packet = _enriched_packet()

    def _document(self, body):
        from newsroom.drafts import render_markdown_document

        return render_markdown_document(self.packet, headline="Mystics fall in Seattle", article=body, excerpt="Recap.")

    def test_claim_audit_embeds_quote_verification(self):
        good = 'Washington struggled. "We just didn\'t take care of the ball tonight," Amoore said.'
        audit = format_claim_evidence_audit(self.packet, article_markdown=self._document(good))
        self.assertIn("quote_verification", audit)
        self.assertFalse(audit["quote_verification"]["hard_fail"])

    def test_claim_audit_flags_fabricated_quote(self):
        bad = 'Amoore said, "We dominated from start to finish and never trailed once."'
        audit = format_claim_evidence_audit(self.packet, article_markdown=self._document(bad))
        self.assertTrue(audit["quote_verification"]["hard_fail"])

    def test_qa_fake_quote_risk_is_transcript_aware(self):
        good_md = self._document('Washington struggled. "We just didn\'t take care of the ball tonight," Amoore said.')
        report = format_editorial_qa_report(self.packet, article_markdown=good_md)
        self.assertNotIn("fake_quote_risk", report["item_reports"]["main_article"]["issue_flags"])

        bad_md = self._document('Amoore said, "We dominated from start to finish and never trailed once."')
        bad_report = format_editorial_qa_report(self.packet, article_markdown=bad_md)
        self.assertIn("fake_quote_risk", bad_report["item_reports"]["main_article"]["issue_flags"])


class QuoteTimestampTests(unittest.TestCase):
    def setUp(self):
        self.packet = _enriched_packet()

    def test_verified_quote_carries_timestamp_and_link(self):
        # PRESSER_LINES[1] is the second segment -> start 3s (segments at i*3).
        body = 'The message was clear: "Amoore set the tone early and we followed her lead."'
        result = verify_quotes(body, self.packet)
        quote = result["quotes"][0]
        self.assertTrue(quote["verified"])
        self.assertEqual(quote["timestamp"], "00:03")
        self.assertEqual(quote["source_link"], "https://www.youtube.com/watch?v=PRES1&t=3s")
        self.assertTrue(result["used_segments"])
        self.assertIn("source_link", result["used_segments"][0])


class NameValidationTests(unittest.TestCase):
    def setUp(self):
        self.packet = _enriched_packet()

    def test_wrong_head_coach_name_hard_fails(self):
        # Real coach is Sydney Johnson; "Cindy Johnson" is the 2026-05-29 live error.
        result = validate_person_names(self.packet, "Coach Cindy Johnson spoke about shot selection.")
        self.assertTrue(result["hard_fail"])
        self.assertTrue(result["requires_external_review"])
        self.assertTrue(any(f["name"] == "Cindy Johnson" for f in result["flagged_names"]))

    def test_correct_head_coach_not_flagged(self):
        result = validate_person_names(self.packet, "Coach Sydney Johnson spoke after the game.")
        self.assertFalse(result["hard_fail"])
        self.assertEqual(result["flagged_names"], [])

    def test_known_player_speaker_not_flagged(self):
        result = validate_person_names(self.packet, "Georgia Amoore said the team needs cleaner looks.")
        self.assertFalse(result["requires_external_review"])

    def test_invented_speaker_flagged_for_review(self):
        result = validate_person_names(self.packet, "Jane Quartermaine said the defense looked sharp.")
        self.assertTrue(result["requires_external_review"])
        self.assertFalse(result["hard_fail"])
        self.assertTrue(any(f["context"] == "speaker" for f in result["flagged_names"]))

    def test_audit_embeds_name_validation(self):
        from newsroom.drafts import render_markdown_document

        doc = render_markdown_document(
            self.packet, headline="Mystics fall", article="Coach Cindy Johnson talked about the loss.", excerpt="x"
        )
        audit = format_claim_evidence_audit(self.packet, article_markdown=doc)
        self.assertIn("name_validation", audit)
        self.assertTrue(audit["name_validation"]["hard_fail"])


if __name__ == "__main__":
    unittest.main()
