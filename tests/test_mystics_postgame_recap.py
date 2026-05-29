from __future__ import annotations

import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

import ingestion.mystics_postgame_recap as cli_module
import newsroom.schemas as schemas
from ingestion.espn_mystics import load_fixture_payload
from ingestion.mystics_normalizer import build_postgame_packet
from ingestion.mystics_postgame_recap import main
from newsroom.assets import format_asset_index, generate_editorial_assets, write_editorial_assets
from newsroom.claim_audit import (
    format_claim_evidence_audit,
    load_claim_evidence_audit,
    write_claim_evidence_audit,
)
from newsroom.discord_review import (
    EDITOR_CHECKLIST,
    format_discord_review_package,
    write_discord_review_package,
)
from newsroom.drafts import render_markdown_draft, write_outputs
from newsroom.external_review import (
    format_external_editor_decision_summary,
    format_external_editor_review_packet,
    ingest_external_editor_response,
    load_external_editor_prompt,
    load_external_editor_response,
    normalize_external_editor_response,
    validate_external_editor_response,
    write_external_editor_review_packet,
)
from newsroom.memory import load_mystics_memory
from newsroom.qa import (
    QA_RECOMMENDATIONS,
    QA_SCORE_CATEGORIES,
    format_editorial_qa_report,
    write_editorial_qa_report,
)
from newsroom.story_angles import select_story_angles


FIXTURE = Path("tests/fixtures/espn_mystics_postgame_401856918.json")
EXTERNAL_RESPONSE_FIXTURE = Path("tests/fixtures/claude_external_editor_response_401856918.json")

READER_FACING_INTERNAL_PHRASES = (
    "packet",
    "top-ranked read",
    "verified espn packet",
    "recap should",
    "fake certainty",
    "without invented intent",
)

UNSUPPORTED_CAUSALITY_MARKERS = (
    "established the terms",
    "established their own rhythm",
    "teaching points",
)


class MysticsPostgameRecapTests(unittest.TestCase):
    def _reader_facing_article_text(self, markdown: str) -> str:
        return markdown.split("**Excerpt:**", 1)[0]

    def _reader_facing_asset_text(self, assets: dict[str, object]) -> str:
        parts = [
            str(assets.get("short_recap") or ""),
            str(assets.get("push_alert") or ""),
            str(assets.get("newsletter_blurb") or ""),
            str(assets.get("seo_summary") or ""),
            str(assets.get("social_caption") or ""),
        ]
        for takeaway in assets.get("takeaways") or []:
            if isinstance(takeaway, dict):
                parts.append(str(takeaway.get("title") or ""))
                parts.append(str(takeaway.get("explanation") or ""))
        for headline in assets.get("headline_candidates") or []:
            if isinstance(headline, dict):
                parts.append(str(headline.get("headline") or ""))
        return "\n".join(parts)

    def _sentence_with_text(self, audit: dict[str, object], text_snippet: str) -> dict[str, object]:
        for sentence in audit.get("sentence_map") or []:
            if isinstance(sentence, dict) and text_snippet in str(sentence.get("text") or ""):
                return sentence
        self.fail(f"Expected sentence containing {text_snippet!r}")

    def _sentence_with_id(self, audit: dict[str, object], sentence_id: str) -> dict[str, object]:
        for sentence in audit.get("sentence_map") or []:
            if isinstance(sentence, dict) and sentence.get("sentence_id") == sentence_id:
                return sentence
        self.fail(f"Expected sentence_id {sentence_id!r}")

    def _schema_artifacts(self) -> dict[str, object]:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        article = render_markdown_draft(packet)
        assets = generate_editorial_assets(packet)
        asset_paths = {
            "headline_candidates": Path("drafts/mystics/assets/mystics-headlines-401856918.json"),
            "newsletter_blurb": Path("drafts/mystics/assets/mystics-newsletter-blurb-401856918.md"),
            "push_alert": Path("drafts/mystics/assets/mystics-push-alert-401856918.txt"),
            "seo_summary": Path("drafts/mystics/assets/mystics-seo-summary-401856918.md"),
            "short_recap": Path("drafts/mystics/assets/mystics-short-recap-401856918.md"),
            "social_caption": Path("drafts/mystics/assets/mystics-social-401856918.txt"),
            "takeaways": Path("drafts/mystics/assets/mystics-takeaways-401856918.md"),
        }
        asset_index = format_asset_index(packet, asset_paths=asset_paths)
        qa_report = format_editorial_qa_report(
            packet,
            article_markdown=article,
            article_markdown_path=Path("drafts/mystics/mystics-postgame-2026-05-19-401856918.md"),
            packet_path=Path("data/packets/mystics_postgame_401856918.json"),
            assets=assets,
            asset_paths=asset_paths,
        )
        claim_audit = format_claim_evidence_audit(
            packet,
            article_markdown=article,
            article_markdown_path=Path("drafts/mystics/mystics-postgame-2026-05-19-401856918.md"),
            packet_path=Path("data/packets/mystics_postgame_401856918.json"),
            assets=assets,
            asset_paths=asset_paths,
        )
        external_packet = format_external_editor_review_packet(
            packet,
            article_markdown=article,
            article_markdown_path=Path("drafts/mystics/mystics-postgame-2026-05-19-401856918.md"),
            assets=assets,
            asset_paths=asset_paths,
            qa_report=qa_report,
            qa_report_path=Path("drafts/mystics/qa/mystics-qa-401856918.json"),
        )
        external_response = load_external_editor_response(EXTERNAL_RESPONSE_FIXTURE)
        normalized_response = normalize_external_editor_response(
            external_response,
            event_id="401856918",
            source_response_path=EXTERNAL_RESPONSE_FIXTURE,
        )
        decision = format_external_editor_decision_summary(
            normalized_response,
            source_response_path=EXTERNAL_RESPONSE_FIXTURE,
            normalized_response_path=Path("drafts/mystics/external_review/responses/mystics-external-editor-response-401856918.json"),
        )
        discord_package = format_discord_review_package(
            packet,
            article_markdown_path=Path("drafts/mystics/mystics-postgame-2026-05-19-401856918.md"),
            packet_path=Path("data/packets/mystics_postgame_401856918.json"),
            qa_report_path=Path("drafts/mystics/qa/mystics-qa-401856918.json"),
            qa_report=qa_report,
            claim_audit_path=Path("drafts/mystics/claim_audit/mystics-claim-audit-401856918.json"),
            claim_audit=claim_audit,
            external_editor_packet_path=Path("drafts/mystics/external_review/mystics-external-review-401856918.json"),
            external_editor_decision_path=Path("drafts/mystics/external_review/mystics-external-editor-decision-401856918.json"),
            external_editor_decision=decision,
        )
        return {
            "packet": packet,
            "asset_index": asset_index,
            "qa_report": qa_report,
            "claim_audit": claim_audit,
            "external_packet": external_packet,
            "external_response": external_response,
            "normalized_response": normalized_response,
            "decision": decision,
            "discord_package": discord_package,
        }

    def test_cli_module_reexports_public_helpers(self) -> None:
        self.assertIs(cli_module.build_postgame_packet, build_postgame_packet)
        self.assertIs(cli_module.load_fixture_payload, load_fixture_payload)
        self.assertIs(cli_module.render_markdown_draft, render_markdown_draft)
        self.assertIs(cli_module.format_discord_review_package, format_discord_review_package)

    def test_schema_validators_accept_current_artifacts_and_extra_keys(self) -> None:
        artifacts = self._schema_artifacts()
        packet = artifacts["packet"]
        asset_index = artifacts["asset_index"]

        self.assertIs(schemas.validate_normalized_game_packet(packet), packet)
        self.assertIs(schemas.validate_story_angles(packet["story_angles"]), packet["story_angles"])
        self.assertIs(schemas.validate_story_angle(packet["story_angles"][0]), packet["story_angles"][0])
        self.assertIs(schemas.validate_asset_index(asset_index), asset_index)
        self.assertIs(schemas.validate_qa_report(artifacts["qa_report"]), artifacts["qa_report"])
        self.assertIs(schemas.validate_claim_evidence_audit(artifacts["claim_audit"]), artifacts["claim_audit"])
        self.assertIs(schemas.validate_external_editor_packet(artifacts["external_packet"]), artifacts["external_packet"])
        self.assertIs(schemas.validate_external_editor_response(artifacts["external_response"]), artifacts["external_response"])
        self.assertIs(
            schemas.validate_normalized_external_editor_response(artifacts["normalized_response"]),
            artifacts["normalized_response"],
        )
        self.assertIs(schemas.validate_external_editor_decision_summary(artifacts["decision"]), artifacts["decision"])
        self.assertIs(schemas.validate_discord_review_package(artifacts["discord_package"]), artifacts["discord_package"])

        packet["future_extra_key"] = {"allowed": True}
        asset_index["future_extra_key"] = {"allowed": True}
        self.assertIs(schemas.validate_normalized_game_packet(packet), packet)
        self.assertIs(schemas.validate_asset_index(asset_index), asset_index)

    def test_schema_validators_reject_bad_packet_and_story_angle_shapes(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        broken_packet = copy.deepcopy(packet)
        broken_packet.pop("game")

        with self.assertRaisesRegex(ValueError, "packet missing required key: game"):
            schemas.validate_normalized_game_packet(broken_packet)

        broken_angles = copy.deepcopy(packet["story_angles"])
        broken_angles[0]["confidence"] = True

        with self.assertRaisesRegex(ValueError, r"story_angles\[0\]\.confidence must be a number"):
            schemas.validate_story_angles(broken_angles)

    def test_schema_validators_reject_bad_review_asset_and_qa_shapes(self) -> None:
        artifacts = self._schema_artifacts()

        broken_asset_index = copy.deepcopy(artifacts["asset_index"])
        broken_asset_index["generated_asset_paths"] = []
        with self.assertRaisesRegex(ValueError, "asset_index.generated_asset_paths must be an object"):
            schemas.validate_asset_index(broken_asset_index)

        broken_qa = copy.deepcopy(artifacts["qa_report"])
        broken_qa["item_reports"]["main_article"]["scores"]["factual_safety"] = 101
        with self.assertRaisesRegex(ValueError, "qa_report.item_reports.main_article.scores.factual_safety must be <= 100"):
            schemas.validate_qa_report(broken_qa)

        broken_discord = copy.deepcopy(artifacts["discord_package"])
        broken_discord["summary_message"] = broken_discord["summary_message"].replace(
            "Human review required before publishing.",
            "Ready now.",
        )
        with self.assertRaisesRegex(ValueError, "human-review-required note"):
            schemas.validate_discord_review_package(broken_discord)

    def test_schema_validators_reject_bad_external_review_shapes(self) -> None:
        artifacts = self._schema_artifacts()

        broken_external_packet = copy.deepcopy(artifacts["external_packet"])
        broken_external_packet["no_auto_publish"] = False
        with self.assertRaisesRegex(ValueError, "external_editor_packet.no_auto_publish must be True"):
            schemas.validate_external_editor_packet(broken_external_packet)

        broken_response = copy.deepcopy(artifacts["external_response"])
        broken_response["article_notes"] = "Looks fine"
        with self.assertRaisesRegex(ValueError, "external_editor_response.article_notes must be a list"):
            schemas.validate_external_editor_response(broken_response)

        broken_envelope = copy.deepcopy(artifacts["normalized_response"])
        broken_envelope["human_editor_required"] = False
        with self.assertRaisesRegex(ValueError, "human_editor_required must be True"):
            schemas.validate_normalized_external_editor_response(broken_envelope)

        broken_decision = copy.deepcopy(artifacts["decision"])
        broken_decision["publish_blockers_count"] = -1
        with self.assertRaisesRegex(ValueError, "publish_blockers_count must be >= 0"):
            schemas.validate_external_editor_decision_summary(broken_decision)

    def test_memory_files_load_correctly(self) -> None:
        memory = load_mystics_memory()

        self.assertEqual(memory["missing_files"], [])
        self.assertEqual(memory["load_errors"], [])
        self.assertIn("narratives", memory["season_narratives"])
        self.assertIn("profiles", memory["player_profiles"])
        self.assertIn("storylines", memory["recent_storylines"])
        self.assertIn("rules", memory["editorial_rules"])

    def test_missing_memory_files_fail_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = load_mystics_memory(Path(tmp))
            packet = build_postgame_packet(load_fixture_payload(FIXTURE), memory_dir=Path(tmp))

        self.assertEqual(
            sorted(memory["missing_files"]),
            [
                "editorial_rules.json",
                "player_profiles.json",
                "recent_storylines.json",
                "season_narratives.json",
            ],
        )
        self.assertEqual(memory["load_errors"], [])
        self.assertEqual(len(packet["story_angles"]), 3)
        self.assertTrue(any("Missing memory files" in flag for angle in packet["story_angles"] for flag in angle["risk_flags"]))

    def test_fixture_normalizes_recent_completed_game(self) -> None:
        payloads = load_fixture_payload(FIXTURE)
        packet = build_postgame_packet(payloads, retrieved_at="2026-05-24T22:30:00Z")

        self.assertEqual(packet["schema_version"], "mystics-postgame-recap/v0.2")
        self.assertEqual(packet["game"]["id"], "401856918")
        self.assertEqual(packet["game"]["status"]["description"], "Final")
        self.assertEqual(packet["game"]["venue"], "College Park Center")
        self.assertEqual(packet["writer_profile"]["name"], "Maya Brooks")
        self.assertIn("memory", packet)
        self.assertIn("story_angles", packet)

        mystics = next(team for team in packet["game"]["teams"] if team["id"] == "16")
        self.assertEqual(mystics["score"], 69)
        self.assertEqual(mystics["team_stats"]["Rebounds"], "24")
        self.assertEqual(mystics["team_stats"]["Total Turnovers"], "19")
        self.assertGreaterEqual(len(mystics["box_score"]), 5)

        self.assertEqual(packet["game"]["scoring_by_quarter"][0]["WSH"], 9)
        self.assertTrue(packet["game"]["play_by_play"]["available"])
        self.assertEqual(packet["game"]["play_by_play"]["scoring_play_count"], 6)

    def test_narrative_signals_include_required_angles(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        narrative = packet["narrative"]

        self.assertEqual(narrative["final_score"], "Dallas Wings 92, Washington Mystics 69")
        self.assertEqual(narrative["result"], "loss")
        self.assertEqual(narrative["biggest_scoring_run"]["points"], 10)
        self.assertIn("10 unanswered", narrative["biggest_scoring_run"]["summary"])
        self.assertEqual(narrative["key_quarter_or_turning_point"]["label"], "Q3")
        self.assertEqual(narrative["stat_edges"]["rebounds"]["edge"], "Dallas Wings")
        self.assertEqual(narrative["stat_edges"]["turnovers"]["mystics"], 19)
        self.assertEqual(narrative["stat_edges"]["bench_points"]["mystics"], 21)
        self.assertEqual(len(narrative["likely_article_angles"]), 3)

    def test_story_angle_selector_returns_three_ranked_angles_with_required_fields(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        angles = select_story_angles(packet)
        required = {"angle_title", "angle_summary", "confidence", "supporting_signals", "risk_flags"}

        self.assertEqual(len(angles), 3)
        self.assertEqual(angles, sorted(angles, key=lambda item: item["confidence"], reverse=True))
        for angle in angles:
            self.assertTrue(required.issubset(angle))
            self.assertIsInstance(angle["supporting_signals"], list)
            self.assertIsInstance(angle["risk_flags"], list)
            self.assertGreaterEqual(angle["confidence"], 0)
            self.assertLessEqual(angle["confidence"], 1)

    def test_story_angle_selector_flags_weak_or_incomplete_data(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        packet["game"]["play_by_play"] = {
            "available": False,
            "play_count": 0,
            "scoring_play_count": 0,
            "scoring_plays": [],
            "notable_plays": [],
            "last_play": None,
        }
        packet["narrative"] = {
            **packet["narrative"],
            "biggest_scoring_run": {
                "points": 0,
                "summary": "Play-by-play did not expose a meaningful scoring run.",
            },
        }

        angles = select_story_angles(packet)
        risk_flags = [flag for angle in angles for flag in angle["risk_flags"]]

        self.assertTrue(any("Play-by-play unavailable" in flag for flag in risk_flags))
        self.assertTrue(any("No meaningful scoring run" in flag for flag in risk_flags))

    def test_markdown_draft_is_expected_length_and_not_publish_action(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        markdown = render_markdown_draft(packet)
        body = markdown.split("**Excerpt:**", 1)[0]
        words = re.findall(r"\b[\w'-]+\b", body)

        self.assertGreaterEqual(len(words), 600)
        self.assertLessEqual(len(words), 800)
        self.assertIn("By Maya Brooks", markdown)
        self.assertIn("status: \"draft\"", markdown)
        self.assertIn("## Narrative Signals", markdown)
        self.assertIn("## Editorial Notes", markdown)
        self.assertIn("Selected angle:", markdown)
        self.assertIn("Alternate angles:", markdown)
        self.assertIn("Key supporting signals:", markdown)
        self.assertIn("Risk flags:", markdown)
        self.assertIn("Source event ID: 401856918", markdown)
        self.assertIn("Generated timestamp:", markdown)
        self.assertNotIn("published", markdown.lower())

    def test_markdown_draft_avoids_internal_and_unsupported_phrasing(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        markdown = render_markdown_draft(packet)
        article_text = self._reader_facing_article_text(markdown).lower()

        for phrase in READER_FACING_INTERNAL_PHRASES:
            self.assertNotIn(phrase, article_text)
        for phrase in UNSUPPORTED_CAUSALITY_MARKERS:
            self.assertNotIn(phrase, article_text)

    def test_markdown_draft_surfaces_top_mystics_performer_before_opponent_star(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        markdown = render_markdown_draft(packet)
        article_text = self._reader_facing_article_text(markdown).lower()
        mystics_performer = next(
            performer
            for performer in packet["narrative"]["top_performers"]
            if performer["team"] == "Washington Mystics"
        )
        opponent_performer = next(
            performer
            for performer in packet["narrative"]["top_performers"]
            if performer["team"] != "Washington Mystics"
        )
        mystics_name = mystics_performer["player"].lower()
        opponent_name = opponent_performer["player"].lower()

        self.assertIn(mystics_name, article_text)
        self.assertIn(opponent_name, article_text)
        self.assertLess(article_text.index(mystics_name), article_text.index(opponent_name))

    def test_write_outputs_uses_mystics_draft_directory(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path, draft_path = write_outputs(
                packet,
                packet_dir=root / "data" / "packets",
                draft_dir=root / "drafts" / "mystics",
            )

            self.assertTrue(packet_path.exists())
            self.assertTrue(draft_path.exists())
            self.assertEqual(draft_path.parent.name, "mystics")
            self.assertIn("mystics_postgame_401856918.json", packet_path.name)
            self.assertIn("mystics-postgame-2026-05-19-401856918.md", draft_path.name)

    def test_editorial_assets_meet_generation_contract(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        assets = generate_editorial_assets(packet)
        selected_risk_flags = packet["story_angles"][0]["risk_flags"]

        self.assertEqual(len(assets["headline_candidates"]), 5)
        self.assertLessEqual(len(assets["push_alert"]), 160)
        self.assertEqual(len(assets["takeaways"]), 3)
        self.assertTrue(assets["seo_summary"])
        self.assertNotIn("\n", assets["seo_summary"])
        self.assertIn(packet["narrative"]["final_score"], assets["social_caption"])
        self.assertLessEqual(assets["social_caption"].count("#"), 2)

        for takeaway in assets["takeaways"]:
            self.assertTrue(takeaway["title"])
            self.assertTrue(takeaway["explanation"])
        for headline in assets["headline_candidates"]:
            self.assertTrue({"headline", "tone", "confidence", "risk_flags"}.issubset(headline))
            for risk_flag in selected_risk_flags:
                self.assertIn(risk_flag, headline["risk_flags"])

    def test_editorial_assets_avoid_internal_review_language(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        assets = generate_editorial_assets(packet)
        reader_text = self._reader_facing_asset_text(assets).lower()

        for phrase in READER_FACING_INTERNAL_PHRASES:
            self.assertNotIn(phrase, reader_text)
        for phrase in UNSUPPORTED_CAUSALITY_MARKERS:
            self.assertNotIn(phrase, reader_text)

    def test_editorial_assets_preserve_core_facts_and_lengths(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        assets = generate_editorial_assets(packet)
        reader_text = self._reader_facing_asset_text(assets)
        opponent = packet["game"]["teams"][0]
        if opponent["name"] == "Washington Mystics":
            opponent = packet["game"]["teams"][1]
        top_mystic = next(
            performer
            for performer in packet["narrative"]["top_performers"]
            if performer["team"] == "Washington Mystics"
        )

        self.assertIn(packet["narrative"]["final_score"], reader_text)
        self.assertIn(opponent["name"], reader_text)
        self.assertIn(top_mystic["player"], reader_text)
        self.assertGreaterEqual(len(re.findall(r"\b[\w'-]+\b", assets["short_recap"])), 120)
        self.assertLessEqual(len(re.findall(r"\b[\w'-]+\b", assets["short_recap"])), 180)
        self.assertGreaterEqual(len(re.findall(r"\b[\w'-]+\b", assets["newsletter_blurb"])), 75)
        self.assertLessEqual(len(re.findall(r"\b[\w'-]+\b", assets["newsletter_blurb"])), 120)
        self.assertLessEqual(len(assets["push_alert"]), 160)
        self.assertLessEqual(assets["social_caption"].count("#"), 2)

    def test_write_editorial_assets_creates_files_and_index(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset_paths, index_path = write_editorial_assets(
                packet,
                asset_dir=root / "drafts" / "mystics" / "assets",
                generated_at="2026-05-24T22:30:00Z",
            )

            expected_assets = {
                "short_recap",
                "takeaways",
                "push_alert",
                "newsletter_blurb",
                "seo_summary",
                "social_caption",
                "headline_candidates",
            }
            self.assertEqual(set(asset_paths), expected_assets)
            for path in asset_paths.values():
                self.assertTrue(path.exists())
                self.assertEqual(path.parent.name, "assets")

            headline_payload = json.loads(asset_paths["headline_candidates"].read_text())
            self.assertEqual(len(headline_payload), 5)
            self.assertLessEqual(len(asset_paths["push_alert"].read_text().strip()), 160)
            self.assertEqual(
                len([line for line in asset_paths["takeaways"].read_text().splitlines() if line.startswith("- ")]),
                3,
            )
            self.assertIn(packet["narrative"]["final_score"], asset_paths["social_caption"].read_text())
            self.assertTrue(asset_paths["seo_summary"].read_text().strip())

            index = json.loads(index_path.read_text())
            self.assertEqual(index["event_id"], "401856918")
            self.assertEqual(index["generation_timestamp"], "2026-05-24T22:30:00Z")
            self.assertEqual(index["selected_story_angle"], packet["story_angles"][0])
            self.assertEqual(set(index["generated_asset_paths"]), expected_assets)
            for key, path in asset_paths.items():
                self.assertEqual(index["generated_asset_paths"][key], str(path))
            for risk_flag in packet["story_angles"][0]["risk_flags"]:
                self.assertIn(risk_flag, index["risk_summary"]["flags"])

    def test_editorial_qa_report_scores_all_generated_items(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        assets = generate_editorial_assets(packet)
        report = format_editorial_qa_report(packet, assets=assets)
        expected_items = {
            "main_article",
            "short_recap",
            "takeaways",
            "push_alert",
            "newsletter_blurb",
            "seo_summary",
            "social_caption",
            "headline_candidates",
        }

        self.assertEqual(set(report["item_reports"]), expected_items)
        self.assertEqual(report["score_categories"], QA_SCORE_CATEGORIES)
        self.assertIn(report["overall_recommendation"], QA_RECOMMENDATIONS)
        self.assertTrue(report["advisory_only"])
        for item in report["item_reports"].values():
            self.assertEqual(set(item["scores"]), set(QA_SCORE_CATEGORIES))
            for score in item["scores"].values():
                self.assertIsInstance(score, int)
                self.assertGreaterEqual(score, 0)
                self.assertLessEqual(score, 100)

    def test_editorial_qa_flags_obvious_quality_problems(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        bad_article = (
            "Mystics update. You won't believe this shocking postgame disaster. "
            "\"We wanted it more,\" a player said after the game. "
            "This season-long trend proves the team culture is broken."
        )
        bad_assets = {
            "push_alert": "You won't believe this shocking Mystics disaster " + ("x" * 170),
            "social_caption": "Mystics update.",
        }

        report = format_editorial_qa_report(packet, article_markdown=bad_article, assets=bad_assets)
        flags = {
            flag
            for item in report["item_reports"].values()
            for flag in item["issue_flags"]
        }

        self.assertIn("missing_score", flags)
        self.assertIn("missing_opponent", flags)
        self.assertIn("missing_top_performers", flags)
        self.assertIn("unsupported_causality", flags)
        self.assertIn("fake_quote_risk", flags)
        self.assertIn("too_clickbaity", flags)
        self.assertIn("too_long", flags)
        self.assertIn("too_short", flags)
        self.assertIn("social_caption_weak", flags)
        self.assertIn("memory_overreach", flags)
        self.assertIn(report["overall_recommendation"], QA_RECOMMENDATIONS)

    def test_claim_evidence_audit_generates_valid_json(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        assets = generate_editorial_assets(packet)
        article = render_markdown_draft(packet)

        audit = format_claim_evidence_audit(packet, article_markdown=article, assets=assets)
        categories = audit["summary"]["category_counts"]

        self.assertEqual(audit["schema_version"], "mystics-claim-evidence-audit/v0.2")
        self.assertEqual(audit["event_id"], "401856918")
        self.assertTrue(audit["advisory_only"])
        self.assertTrue(audit["human_editor_required"])
        self.assertTrue(audit["no_auto_publish"])
        self.assertEqual(audit["grounding_method_version"], "deterministic-sentence-grounding/v0.1")
        self.assertIn("supported", audit["support_statuses"])
        self.assertGreater(len(audit["sentence_map"]), 0)
        self.assertEqual(audit["sentence_summary"]["total_sentences"], len(audit["sentence_map"]))
        self.assertGreater(audit["summary"]["total_claims"], 0)
        self.assertGreater(categories["supported_by_packet"], 0)
        self.assertIn("main_article", {claim["item_key"] for claim in audit["claims"]})
        self.assertIs(schemas.validate_claim_evidence_audit(audit), audit)

    def test_claim_evidence_audit_maps_final_score_sentence_to_packet_evidence(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        audit = format_claim_evidence_audit(packet, article_markdown=render_markdown_draft(packet))

        sentence = self._sentence_with_text(audit, "final score landing at Dallas Wings 92, Washington Mystics 69")
        evidence_paths = {ref["path"] for ref in sentence["evidence_refs"]}

        self.assertEqual(sentence["support_status"], "supported")
        self.assertIn("final_score", sentence["claim_types"])
        self.assertIn("result", sentence["claim_types"])
        self.assertIn("venue", sentence["claim_types"])
        self.assertIn("date", sentence["claim_types"])
        self.assertIn("narrative.final_score", evidence_paths)
        self.assertIn("game.venue", evidence_paths)

    def test_claim_evidence_audit_maps_top_mystics_performer_sentence_to_packet_evidence(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        audit = format_claim_evidence_audit(packet, article_markdown=render_markdown_draft(packet))

        sentence = self._sentence_with_text(audit, "Georgia Amoore, who finished with 14 points")
        evidence_paths = {ref["path"] for ref in sentence["evidence_refs"]}

        self.assertEqual(sentence["support_status"], "supported")
        self.assertIn("top_mystics_performer", sentence["claim_types"])
        self.assertTrue(any(path.startswith("narrative.top_performers") for path in evidence_paths))

    def test_claim_evidence_audit_maps_team_stat_edge_sentence_to_packet_evidence(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        audit = format_claim_evidence_audit(packet, article_markdown=render_markdown_draft(packet))

        sentence = self._sentence_with_text(audit, "Washington had 19 total turnovers")
        evidence_paths = {ref["path"] for ref in sentence["evidence_refs"]}

        self.assertEqual(sentence["support_status"], "supported")
        self.assertIn("team_stat", sentence["claim_types"])
        self.assertIn("narrative.stat_edges.turnovers", evidence_paths)

    def test_claim_evidence_audit_flags_unsupported_sentence_with_exact_id(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        bad_article = (
            "Washington lost to the Dallas Wings 92-69. "
            "The Mystics lost because of effort. "
            "The official final was Dallas Wings 92, Washington Mystics 69."
        )

        audit = format_claim_evidence_audit(packet, article_markdown=bad_article)
        sentence = self._sentence_with_id(audit, "main_article:s002")

        self.assertEqual(sentence["support_status"], "unsupported")
        self.assertIn("unsupported_interpretation", sentence["claim_types"])
        self.assertIn("unsupported_marker:because of effort", sentence["risk_flags"])
        self.assertEqual(audit["sentence_summary"]["unsupported_sentence_count"], 1)

    def test_claim_evidence_audit_flags_obvious_contradictory_score_and_player_stat(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        bad_article = (
            "Washington beat the Dallas Wings 91-69 at College Park Center on May 19, 2026. "
            "Georgia Amoore finished with 20 points, 2 rebounds, 3 assists."
        )

        audit = format_claim_evidence_audit(packet, article_markdown=bad_article)
        contradictions = [sentence for sentence in audit["sentence_map"] if sentence["support_status"] == "contradiction"]

        self.assertEqual(audit["sentence_summary"]["contradiction_count"], 2)
        self.assertTrue(any("final_score" in sentence["claim_types"] for sentence in contradictions))
        self.assertTrue(any("player_stat" in sentence["claim_types"] for sentence in contradictions))

    def test_claim_evidence_audit_marks_memory_trend_sentence_weak_not_packet_supported(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        article = (
            "Washington lost to the Dallas Wings 92-69. "
            "This season-long trend defines the Mystics identity."
        )

        audit = format_claim_evidence_audit(packet, article_markdown=article)
        sentence = self._sentence_with_text(audit, "season-long trend")

        self.assertEqual(sentence["support_status"], "weak")
        self.assertIn("memory_or_trend_language", sentence["claim_types"])
        self.assertNotEqual(sentence["support_status"], "supported")
        self.assertEqual(audit["sentence_summary"]["weak_sentence_count"], 1)

    def test_claim_evidence_audit_flags_unsupported_interpretation(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        bad_article = (
            "Washington lost to the Dallas Wings 92-69 because of effort. "
            "The official final was Dallas Wings 92, Washington Mystics 69."
        )

        audit = format_claim_evidence_audit(packet, article_markdown=bad_article)
        unsupported = [claim for claim in audit["claims"] if claim["category"] == "unsupported"]

        self.assertTrue(any("because of effort" in claim["claim"] for claim in unsupported))
        self.assertGreater(audit["summary"]["category_counts"]["unsupported"], 0)

    def test_claim_evidence_audit_flags_missing_second_source(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        audit = format_claim_evidence_audit(packet, article_markdown=render_markdown_draft(packet))
        source_gap_claims = [claim for claim in audit["claims"] if claim["category"] == "source_gap"]

        self.assertFalse(audit["source_inventory"]["second_source_present"])
        self.assertFalse(audit["summary"]["second_source_present"])
        self.assertTrue(any("ESPN-only" in claim["claim"] for claim in source_gap_claims))

    def test_claim_evidence_audit_flags_opponent_heavy_copy(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        opponent_heavy_article = (
            "Dallas Wings controlled the night. Dallas Wings guard Paige Bueckers scored. "
            "Jessica Shepard led Dallas Wings on the glass. Aziaha James helped Dallas Wings. "
            "Arike Ogunbowale kept Dallas Wings steady. Dallas Wings won 92-69."
        )

        audit = format_claim_evidence_audit(packet, article_markdown=opponent_heavy_article)
        balance_claims = [claim for claim in audit["claims"] if claim["category"] == "balance_warning"]

        self.assertTrue(balance_claims)
        self.assertGreater(audit["summary"]["opponent_mentions"], audit["summary"]["washington_mentions"])

    def test_claim_evidence_audit_flags_missing_top_mystics_performer(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        no_top_mystic_article = (
            "Washington lost to the Dallas Wings 92-69. "
            "The official final was Dallas Wings 92, Washington Mystics 69. "
            "The recap focuses on turnovers, rebounds, and the team-level score."
        )

        audit = format_claim_evidence_audit(packet, article_markdown=no_top_mystic_article)
        needs_review = [claim for claim in audit["claims"] if claim["category"] == "needs_human_review"]

        self.assertFalse(audit["summary"]["top_mystics_performer_surfaced"])
        self.assertTrue(any("top Mystics performer" in claim["claim"] for claim in needs_review))

    def test_claim_evidence_audit_schema_rejects_malformed_category_counts(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        audit = format_claim_evidence_audit(packet, article_markdown=render_markdown_draft(packet))
        audit["summary"]["category_counts"]["unsupported"] = "one"

        with self.assertRaisesRegex(ValueError, "claim_audit.summary.category_counts.unsupported must be an integer"):
            schemas.validate_claim_evidence_audit(audit)

    def test_claim_evidence_audit_schema_rejects_inconsistent_total_claims(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        audit = format_claim_evidence_audit(packet, article_markdown=render_markdown_draft(packet))
        audit["summary"]["total_claims"] += 1

        with self.assertRaisesRegex(ValueError, r"claim_audit.summary.total_claims must equal len\(claim_audit.claims\)"):
            schemas.validate_claim_evidence_audit(audit)

    def test_claim_evidence_audit_schema_rejects_mismatched_category_counts(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        audit = format_claim_evidence_audit(packet, article_markdown=render_markdown_draft(packet))
        audit["summary"]["category_counts"]["supported_by_packet"] += 1

        with self.assertRaisesRegex(ValueError, "claim_audit.summary.category_counts.supported_by_packet must equal actual claim count"):
            schemas.validate_claim_evidence_audit(audit)

    def test_claim_evidence_audit_schema_rejects_mismatched_warning_count(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        audit = format_claim_evidence_audit(packet, article_markdown=render_markdown_draft(packet))
        audit["summary"]["warning_count"] += 1

        with self.assertRaisesRegex(ValueError, "claim_audit.summary.warning_count must equal actual warning claim count"):
            schemas.validate_claim_evidence_audit(audit)

    def test_claim_evidence_audit_schema_rejects_source_count_mismatch(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        audit = format_claim_evidence_audit(packet, article_markdown=render_markdown_draft(packet))
        audit["source_inventory"]["source_count"] += 1

        with self.assertRaisesRegex(ValueError, r"claim_audit.source_inventory.source_count must equal len\(claim_audit.source_inventory.sources\)"):
            schemas.validate_claim_evidence_audit(audit)

    def test_claim_evidence_audit_schema_rejects_sentence_summary_inconsistency(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        audit = format_claim_evidence_audit(packet, article_markdown=render_markdown_draft(packet))
        audit["sentence_summary"]["status_counts"]["unsupported"] += 1

        with self.assertRaisesRegex(ValueError, "claim_audit.sentence_summary.status_counts.unsupported must equal actual sentence count"):
            schemas.validate_claim_evidence_audit(audit)

    def test_claim_evidence_audit_schema_rejects_unknown_lowest_confidence_sentence_id(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        audit = format_claim_evidence_audit(packet, article_markdown=render_markdown_draft(packet))
        audit["sentence_summary"]["lowest_confidence_sentence_ids"].append("main_article:s999")

        with self.assertRaisesRegex(ValueError, "lowest_confidence_sentence_ids contains unknown sentence_id: main_article:s999"):
            schemas.validate_claim_evidence_audit(audit)

    def test_claim_evidence_audit_schema_allows_extra_keys(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        audit = format_claim_evidence_audit(packet, article_markdown=render_markdown_draft(packet))
        audit["future_extra_key"] = {"allowed": True}
        audit["summary"]["future_extra_key"] = {"allowed": True}
        audit["source_inventory"]["future_extra_key"] = {"allowed": True}
        audit["source_inventory"]["sources"][0]["future_extra_key"] = {"allowed": True}
        audit["claims"][0]["future_extra_key"] = {"allowed": True}
        audit["sentence_summary"]["future_extra_key"] = {"allowed": True}
        audit["sentence_map"][0]["future_extra_key"] = {"allowed": True}
        audit["sentence_map"][0]["evidence_refs"][0]["future_extra_key"] = {"allowed": True}

        self.assertIs(schemas.validate_claim_evidence_audit(audit), audit)

    def test_write_claim_evidence_audit_creates_json(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path, draft_path = write_outputs(
                packet,
                packet_dir=root / "data" / "packets",
                draft_dir=root / "drafts" / "mystics",
            )
            audit_path = write_claim_evidence_audit(
                packet,
                article_markdown_path=draft_path,
                packet_path=packet_path,
                audit_dir=root / "drafts" / "mystics" / "claim_audit",
                generated_at="2026-05-24T22:30:00Z",
            )

            self.assertTrue(audit_path.exists())
            self.assertEqual(audit_path.name, "mystics-claim-audit-401856918.json")
            payload = load_claim_evidence_audit(audit_path, event_id="401856918")
            self.assertEqual(payload["generation_timestamp"], "2026-05-24T22:30:00Z")
            self.assertEqual(payload["article_markdown_path"], str(draft_path))
            self.assertEqual(payload["packet_path"], str(packet_path))

    def test_write_editorial_qa_report_creates_json(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        assets = generate_editorial_assets(packet)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path, draft_path = write_outputs(
                packet,
                packet_dir=root / "data" / "packets",
                draft_dir=root / "drafts" / "mystics",
            )
            asset_paths, _ = write_editorial_assets(
                packet,
                asset_dir=root / "drafts" / "mystics" / "assets",
                assets=assets,
            )
            qa_path = write_editorial_qa_report(
                packet,
                article_markdown_path=draft_path,
                packet_path=packet_path,
                qa_dir=root / "drafts" / "mystics" / "qa",
                assets=assets,
                asset_paths=asset_paths,
                generated_at="2026-05-24T22:30:00Z",
            )

            self.assertTrue(qa_path.exists())
            self.assertEqual(qa_path.name, "mystics-qa-401856918.json")
            payload = json.loads(qa_path.read_text())
            self.assertEqual(payload["event_id"], "401856918")
            self.assertEqual(payload["generation_timestamp"], "2026-05-24T22:30:00Z")
            self.assertIn("main_article", payload["item_reports"])
            self.assertIn("headline_candidates", payload["item_reports"])
            self.assertIn(payload["overall_recommendation"], QA_RECOMMENDATIONS)

    def test_external_editor_prompt_has_required_instructions(self) -> None:
        prompt = load_external_editor_prompt()

        self.assertIn("senior sports editor", prompt)
        self.assertIn("Return structured JSON only", prompt)
        self.assertIn("Do not publish", prompt)
        self.assertIn("Do not", prompt)
        self.assertIn("automatically", prompt)
        self.assertIn("overall_verdict", prompt)
        self.assertIn("recommended_edits", prompt)

    def test_external_editor_packet_includes_article_assets_qa_and_context(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        assets = generate_editorial_assets(packet)
        qa_report = format_editorial_qa_report(packet, assets=assets)
        article = render_markdown_draft(packet)
        review_packet = format_external_editor_review_packet(
            packet,
            article_markdown=article,
            assets=assets,
            qa_report=qa_report,
            qa_report_path=Path("drafts/mystics/qa/mystics-qa-401856918.json"),
            generated_at="2026-05-24T22:30:00Z",
        )

        self.assertIn("Return structured JSON only", review_packet["editor_prompt"])
        self.assertIn("Do not publish", review_packet["editor_prompt"])
        self.assertEqual(review_packet["main_article_markdown"], article)
        self.assertEqual(review_packet["generated_assets"], assets)
        self.assertTrue(review_packet["internal_qa_summary"]["available"])
        self.assertEqual(review_packet["internal_qa_summary"]["overall_recommendation"], qa_report["overall_recommendation"])
        self.assertEqual(review_packet["story_angles"], packet["story_angles"])
        self.assertEqual(review_packet["editorial_rules"], packet["memory"]["editorial_rules"]["rules"])
        self.assertEqual(review_packet["source_event_id"], "401856918")
        self.assertEqual(review_packet["generated_timestamp"], "2026-05-24T22:30:00Z")
        self.assertTrue(review_packet["external_review_only"])
        self.assertTrue(review_packet["no_auto_publish"])
        self.assertTrue(review_packet["no_auto_rewrite"])

    def test_external_editor_packet_omits_assets_and_qa_when_not_requested(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        review_packet = format_external_editor_review_packet(packet)

        self.assertEqual(review_packet["generated_assets"], {})
        self.assertFalse(review_packet["internal_qa_summary"]["available"])
        self.assertIn("final_score", review_packet["normalized_game_packet_summary"])
        self.assertIn("season_narratives", review_packet["memory_context_summary"])

    def test_write_external_editor_review_packet_creates_json(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        assets = generate_editorial_assets(packet)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path, draft_path = write_outputs(
                packet,
                packet_dir=root / "data" / "packets",
                draft_dir=root / "drafts" / "mystics",
            )
            asset_paths, _ = write_editorial_assets(
                packet,
                asset_dir=root / "drafts" / "mystics" / "assets",
                assets=assets,
            )
            qa_path = write_editorial_qa_report(
                packet,
                article_markdown_path=draft_path,
                packet_path=packet_path,
                qa_dir=root / "drafts" / "mystics" / "qa",
                assets=assets,
                asset_paths=asset_paths,
            )
            qa_report = json.loads(qa_path.read_text())
            external_path = write_external_editor_review_packet(
                packet,
                article_markdown_path=draft_path,
                external_review_dir=root / "drafts" / "mystics" / "external_review",
                assets=assets,
                asset_paths=asset_paths,
                qa_report=qa_report,
                qa_report_path=qa_path,
                generated_at="2026-05-24T22:30:00Z",
            )

            self.assertTrue(external_path.exists())
            self.assertEqual(external_path.name, "mystics-external-review-401856918.json")
            payload = json.loads(external_path.read_text())
            self.assertIn("editor_prompt", payload)
            self.assertIn("main_article_markdown", payload)
            self.assertIn("short_recap", payload["generated_assets"])
            self.assertTrue(payload["internal_qa_summary"]["available"])
            self.assertEqual(payload["source_paths"]["qa_report_path"], str(qa_path))

    def test_valid_external_editor_response_ingests_successfully(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            normalized_path, decision_path = ingest_external_editor_response(
                packet,
                source_response_path=EXTERNAL_RESPONSE_FIXTURE,
                external_review_dir=root / "drafts" / "mystics" / "external_review",
                generated_at="2026-05-24T22:30:00Z",
            )

            self.assertTrue(normalized_path.exists())
            self.assertTrue(decision_path.exists())
            self.assertEqual(normalized_path.parent.name, "responses")
            normalized = json.loads(normalized_path.read_text())
            decision = json.loads(decision_path.read_text())
            self.assertEqual(normalized["event_id"], "401856918")
            self.assertEqual(normalized["response"]["overall_verdict"], "approve_with_minor_edits")
            self.assertEqual(decision["overall_verdict"], "approve_with_minor_edits")
            self.assertTrue(decision["safe_to_publish_candidate"])
            self.assertTrue(decision["human_editor_required"])

    def test_external_editor_response_validation_rejects_invalid_verdict(self) -> None:
        response = load_external_editor_response(EXTERNAL_RESPONSE_FIXTURE)
        response["overall_verdict"] = "publish_now"

        with self.assertRaises(ValueError):
            validate_external_editor_response(response)

    def test_external_editor_response_validation_rejects_invalid_confidence(self) -> None:
        response = load_external_editor_response(EXTERNAL_RESPONSE_FIXTURE)
        response["confidence"] = 1.5

        with self.assertRaises(ValueError):
            validate_external_editor_response(response)

    def test_external_editor_response_validation_rejects_missing_required_fields(self) -> None:
        response = load_external_editor_response(EXTERNAL_RESPONSE_FIXTURE)
        response.pop("recommended_edits")

        with self.assertRaises(ValueError):
            validate_external_editor_response(response)

    def test_external_editor_decision_summary_contains_required_fields(self) -> None:
        response = load_external_editor_response(EXTERNAL_RESPONSE_FIXTURE)
        normalized = normalize_external_editor_response(
            response,
            event_id="401856918",
            source_response_path=EXTERNAL_RESPONSE_FIXTURE,
            generated_at="2026-05-24T22:30:00Z",
        )
        decision = format_external_editor_decision_summary(
            normalized,
            source_response_path=EXTERNAL_RESPONSE_FIXTURE,
            normalized_response_path=Path("drafts/mystics/external_review/responses/mystics-external-editor-response-401856918.json"),
            generated_at="2026-05-24T22:30:00Z",
        )
        required = {
            "source_response_path",
            "normalized_response_path",
            "overall_verdict",
            "confidence",
            "publish_blockers_count",
            "unsupported_claims_count",
            "recommended_edits_count",
            "needs_revision",
            "safe_to_publish_candidate",
            "human_editor_required",
            "generated_timestamp",
        }

        self.assertTrue(required.issubset(decision))
        self.assertEqual(decision["publish_blockers_count"], 0)
        self.assertEqual(decision["unsupported_claims_count"], 0)
        self.assertEqual(decision["recommended_edits_count"], 2)
        self.assertFalse(decision["needs_revision"])
        self.assertTrue(decision["safe_to_publish_candidate"])
        self.assertTrue(decision["human_editor_required"])

    def test_external_editor_decision_safe_to_publish_logic(self) -> None:
        response = load_external_editor_response(EXTERNAL_RESPONSE_FIXTURE)
        response["overall_verdict"] = "needs_revision"
        response["publish_blockers"] = []
        normalized = normalize_external_editor_response(
            response,
            event_id="401856918",
            source_response_path=EXTERNAL_RESPONSE_FIXTURE,
        )
        decision = format_external_editor_decision_summary(
            normalized,
            source_response_path=EXTERNAL_RESPONSE_FIXTURE,
            normalized_response_path=Path("normalized.json"),
        )

        self.assertTrue(decision["needs_revision"])
        self.assertFalse(decision["safe_to_publish_candidate"])
        self.assertTrue(decision["human_editor_required"])

        response["overall_verdict"] = "approve"
        response["publish_blockers"] = ["Needs source check before editor approval."]
        normalized = normalize_external_editor_response(
            response,
            event_id="401856918",
            source_response_path=EXTERNAL_RESPONSE_FIXTURE,
        )
        decision = format_external_editor_decision_summary(
            normalized,
            source_response_path=EXTERNAL_RESPONSE_FIXTURE,
            normalized_response_path=Path("normalized.json"),
        )

        self.assertFalse(decision["needs_revision"])
        self.assertFalse(decision["safe_to_publish_candidate"])
        self.assertTrue(decision["human_editor_required"])

    def test_external_editor_response_ingestion_does_not_modify_draft(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, draft_path = write_outputs(
                packet,
                packet_dir=root / "data" / "packets",
                draft_dir=root / "drafts" / "mystics",
            )
            before = draft_path.read_text()
            ingest_external_editor_response(
                packet,
                source_response_path=EXTERNAL_RESPONSE_FIXTURE,
                external_review_dir=root / "drafts" / "mystics" / "external_review",
            )
            after = draft_path.read_text()

            self.assertEqual(before, after)

    def test_discord_review_package_has_required_fields_and_content(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        package = format_discord_review_package(
            packet,
            article_markdown_path=Path("drafts/mystics/mystics-postgame-2026-05-19-401856918.md"),
            packet_path=Path("data/packets/mystics_postgame_401856918.json"),
        )
        required = {
            "thread_title",
            "summary_message",
            "editor_checklist",
            "article_markdown_path",
            "packet_path",
            "risk_flags",
            "selected_angle",
            "alternate_angles",
            "recommended_status",
        }

        self.assertTrue(required.issubset(package))
        self.assertIn("[Mystics Recap]", package["thread_title"])
        self.assertIn("2026-05-19", package["thread_title"])
        self.assertIn("401856918", package["thread_title"])
        self.assertIn("Human review required before publishing.", package["summary_message"])
        self.assertIn("Final score: Dallas Wings 92, Washington Mystics 69", package["summary_message"])
        self.assertIn("Draft path:", package["summary_message"])
        self.assertIn("Packet path:", package["summary_message"])
        self.assertEqual(package["editor_checklist"], EDITOR_CHECKLIST)
        self.assertEqual(package["selected_angle"], packet["story_angles"][0])
        self.assertEqual(package["alternate_angles"], packet["story_angles"][1:])
        self.assertEqual(package["risk_flags"], packet["story_angles"][0]["risk_flags"])
        self.assertEqual(package["recommended_status"], "human_review_required")

    def test_discord_review_package_includes_qa_fields_when_available(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        report = format_editorial_qa_report(packet, assets=generate_editorial_assets(packet))
        package = format_discord_review_package(
            packet,
            article_markdown_path=Path("drafts/mystics/mystics-postgame-2026-05-19-401856918.md"),
            packet_path=Path("data/packets/mystics_postgame_401856918.json"),
            qa_report_path=Path("drafts/mystics/qa/mystics-qa-401856918.json"),
            qa_report=report,
        )

        self.assertEqual(package["qa_report_path"], "drafts/mystics/qa/mystics-qa-401856918.json")
        self.assertEqual(package["overall_recommendation"], report["overall_recommendation"])
        self.assertEqual(package["lowest_scoring_items"], report["summary"]["lowest_scoring_items"])
        self.assertEqual(package["top_issue_flags"], report["summary"]["top_issue_flags"])
        self.assertIn("QA report path:", package["summary_message"])
        self.assertIn("QA recommendation:", package["summary_message"])

    def test_discord_review_package_includes_external_editor_fields_when_available(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        package = format_discord_review_package(
            packet,
            article_markdown_path=Path("drafts/mystics/mystics-postgame-2026-05-19-401856918.md"),
            packet_path=Path("data/packets/mystics_postgame_401856918.json"),
            external_editor_packet_path=Path("drafts/mystics/external_review/mystics-external-review-401856918.json"),
        )

        self.assertEqual(
            package["external_editor_packet_path"],
            "drafts/mystics/external_review/mystics-external-review-401856918.json",
        )
        self.assertTrue(package["recommended_external_review"])
        self.assertIn("External editor packet:", package["summary_message"])

    def test_discord_review_package_includes_external_decision_fields_when_available(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        response = load_external_editor_response(EXTERNAL_RESPONSE_FIXTURE)
        normalized = normalize_external_editor_response(
            response,
            event_id="401856918",
            source_response_path=EXTERNAL_RESPONSE_FIXTURE,
        )
        decision = format_external_editor_decision_summary(
            normalized,
            source_response_path=EXTERNAL_RESPONSE_FIXTURE,
            normalized_response_path=Path("drafts/mystics/external_review/responses/mystics-external-editor-response-401856918.json"),
        )
        package = format_discord_review_package(
            packet,
            article_markdown_path=Path("drafts/mystics/mystics-postgame-2026-05-19-401856918.md"),
            packet_path=Path("data/packets/mystics_postgame_401856918.json"),
            external_editor_decision_path=Path("drafts/mystics/external_review/mystics-external-editor-decision-401856918.json"),
            external_editor_decision=decision,
        )

        self.assertEqual(
            package["external_editor_decision_path"],
            "drafts/mystics/external_review/mystics-external-editor-decision-401856918.json",
        )
        self.assertEqual(package["external_editor_verdict"], "approve_with_minor_edits")
        self.assertEqual(package["external_editor_confidence"], 0.86)
        self.assertEqual(package["external_editor_publish_blockers_count"], 0)
        self.assertFalse(package["external_editor_needs_revision"])
        self.assertTrue(package["human_editor_required"])

    def test_discord_review_json_is_created_when_requested(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path, draft_path = write_outputs(
                packet,
                packet_dir=root / "data" / "packets",
                draft_dir=root / "drafts" / "mystics",
            )
            review_path = write_discord_review_package(
                packet,
                article_markdown_path=draft_path,
                packet_path=packet_path,
                review_dir=root / "drafts" / "mystics" / "review",
            )

            self.assertTrue(review_path.exists())
            self.assertEqual(review_path.name, "mystics-postgame-2026-05-19-401856918-review.json")
            payload = json.loads(review_path.read_text())
            self.assertIn("Human review required before publishing.", payload["summary_message"])
            self.assertEqual(payload["editor_checklist"], EDITOR_CHECKLIST)

    def test_discord_review_json_auto_includes_existing_qa_report(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path, draft_path = write_outputs(
                packet,
                packet_dir=root / "data" / "packets",
                draft_dir=root / "drafts" / "mystics",
            )
            qa_path = write_editorial_qa_report(
                packet,
                article_markdown_path=draft_path,
                packet_path=packet_path,
                qa_dir=root / "drafts" / "mystics" / "qa",
            )
            review_path = write_discord_review_package(
                packet,
                article_markdown_path=draft_path,
                packet_path=packet_path,
                review_dir=root / "drafts" / "mystics" / "review",
            )

            self.assertTrue(qa_path.exists())
            payload = json.loads(review_path.read_text())
            self.assertEqual(payload["qa_report_path"], str(qa_path))
            self.assertIn(payload["overall_recommendation"], QA_RECOMMENDATIONS)
            self.assertIn("lowest_scoring_items", payload)
            self.assertIn("top_issue_flags", payload)

    def test_discord_review_rejects_wrong_event_qa_report(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path, draft_path = write_outputs(
                packet,
                packet_dir=root / "data" / "packets",
                draft_dir=root / "drafts" / "mystics",
            )
            qa_path = write_editorial_qa_report(
                packet,
                article_markdown_path=draft_path,
                packet_path=packet_path,
                qa_dir=root / "drafts" / "mystics" / "qa",
            )
            qa_payload = json.loads(qa_path.read_text())
            qa_payload["event_id"] = "wrong-event"
            qa_path.write_text(json.dumps(qa_payload, indent=2, sort_keys=True) + "\n")

            with self.assertRaises(ValueError) as ctx:
                write_discord_review_package(
                    packet,
                    article_markdown_path=draft_path,
                    packet_path=packet_path,
                    review_dir=root / "drafts" / "mystics" / "review",
                )

            self.assertIn(str(qa_path), str(ctx.exception))
            self.assertIn("event_id 'wrong-event'", str(ctx.exception))
            self.assertIn("expected active packet event_id '401856918'", str(ctx.exception))

    def test_discord_review_json_auto_includes_existing_claim_audit(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path, draft_path = write_outputs(
                packet,
                packet_dir=root / "data" / "packets",
                draft_dir=root / "drafts" / "mystics",
            )
            audit_path = write_claim_evidence_audit(
                packet,
                article_markdown_path=draft_path,
                packet_path=packet_path,
                audit_dir=root / "drafts" / "mystics" / "claim_audit",
            )
            review_path = write_discord_review_package(
                packet,
                article_markdown_path=draft_path,
                packet_path=packet_path,
                review_dir=root / "drafts" / "mystics" / "review",
            )

            payload = json.loads(review_path.read_text())
            self.assertEqual(payload["claim_audit_path"], str(audit_path))
            self.assertIn("claim_audit_summary", payload)
            self.assertIn("unsupported_sentence_count", payload["claim_audit_summary"])
            self.assertIn("weak_sentence_count", payload["claim_audit_summary"])
            self.assertIn("contradiction_count", payload["claim_audit_summary"])
            self.assertIn("lowest_confidence_sentence_ids", payload["claim_audit_summary"])
            self.assertIn("Claim audit path:", payload["summary_message"])
            self.assertIn("Claim audit warnings:", payload["summary_message"])
            self.assertIn("Claim grounding unsupported sentences:", payload["summary_message"])

    def test_discord_review_rejects_wrong_event_existing_claim_audit(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path, draft_path = write_outputs(
                packet,
                packet_dir=root / "data" / "packets",
                draft_dir=root / "drafts" / "mystics",
            )
            audit_path = write_claim_evidence_audit(
                packet,
                article_markdown_path=draft_path,
                packet_path=packet_path,
                audit_dir=root / "drafts" / "mystics" / "claim_audit",
            )
            audit_payload = json.loads(audit_path.read_text())
            audit_payload["event_id"] = "wrong-event"
            audit_path.write_text(json.dumps(audit_payload, indent=2, sort_keys=True) + "\n")

            with self.assertRaises(ValueError) as ctx:
                write_discord_review_package(
                    packet,
                    article_markdown_path=draft_path,
                    packet_path=packet_path,
                    review_dir=root / "drafts" / "mystics" / "review",
                )

            self.assertIn(str(audit_path), str(ctx.exception))
            self.assertIn("event_id 'wrong-event'", str(ctx.exception))
            self.assertIn("expected active packet event_id '401856918'", str(ctx.exception))

    def test_discord_review_rejects_malformed_existing_claim_audit(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path, draft_path = write_outputs(
                packet,
                packet_dir=root / "data" / "packets",
                draft_dir=root / "drafts" / "mystics",
            )
            audit_path = write_claim_evidence_audit(
                packet,
                article_markdown_path=draft_path,
                packet_path=packet_path,
                audit_dir=root / "drafts" / "mystics" / "claim_audit",
            )
            audit_payload = json.loads(audit_path.read_text())
            audit_payload["summary"]["category_counts"]["unsupported"] = "one"
            audit_path.write_text(json.dumps(audit_payload, indent=2, sort_keys=True) + "\n")

            with self.assertRaises(ValueError) as ctx:
                write_discord_review_package(
                    packet,
                    article_markdown_path=draft_path,
                    packet_path=packet_path,
                    review_dir=root / "drafts" / "mystics" / "review",
                )

            self.assertIn(str(audit_path), str(ctx.exception))
            self.assertIn("Invalid claim evidence audit", str(ctx.exception))
            self.assertIn("category_counts.unsupported must be an integer", str(ctx.exception))

    def test_discord_review_json_auto_includes_existing_external_editor_packet(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path, draft_path = write_outputs(
                packet,
                packet_dir=root / "data" / "packets",
                draft_dir=root / "drafts" / "mystics",
            )
            external_path = write_external_editor_review_packet(
                packet,
                article_markdown_path=draft_path,
                external_review_dir=root / "drafts" / "mystics" / "external_review",
            )
            review_path = write_discord_review_package(
                packet,
                article_markdown_path=draft_path,
                packet_path=packet_path,
                review_dir=root / "drafts" / "mystics" / "review",
            )

            self.assertTrue(external_path.exists())
            payload = json.loads(review_path.read_text())
            self.assertEqual(payload["external_editor_packet_path"], str(external_path))
            self.assertTrue(payload["recommended_external_review"])
            self.assertIn("External editor packet:", payload["summary_message"])

    def test_discord_review_rejects_malformed_existing_external_editor_packet(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path, draft_path = write_outputs(
                packet,
                packet_dir=root / "data" / "packets",
                draft_dir=root / "drafts" / "mystics",
            )
            external_path = write_external_editor_review_packet(
                packet,
                article_markdown_path=draft_path,
                external_review_dir=root / "drafts" / "mystics" / "external_review",
            )
            external_payload = json.loads(external_path.read_text())
            external_payload["no_auto_publish"] = False
            external_path.write_text(json.dumps(external_payload, indent=2, sort_keys=True) + "\n")

            with self.assertRaises(ValueError) as ctx:
                write_discord_review_package(
                    packet,
                    article_markdown_path=draft_path,
                    packet_path=packet_path,
                    review_dir=root / "drafts" / "mystics" / "review",
                )

            self.assertIn(str(external_path), str(ctx.exception))
            self.assertIn("Invalid external editor packet", str(ctx.exception))
            self.assertIn("no_auto_publish must be True", str(ctx.exception))

    def test_discord_review_json_auto_includes_existing_external_editor_decision(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path, draft_path = write_outputs(
                packet,
                packet_dir=root / "data" / "packets",
                draft_dir=root / "drafts" / "mystics",
            )
            _, decision_path = ingest_external_editor_response(
                packet,
                source_response_path=EXTERNAL_RESPONSE_FIXTURE,
                external_review_dir=root / "drafts" / "mystics" / "external_review",
            )
            review_path = write_discord_review_package(
                packet,
                article_markdown_path=draft_path,
                packet_path=packet_path,
                review_dir=root / "drafts" / "mystics" / "review",
            )

            self.assertTrue(decision_path.exists())
            payload = json.loads(review_path.read_text())
            self.assertEqual(payload["external_editor_decision_path"], str(decision_path))
            self.assertEqual(payload["external_editor_verdict"], "approve_with_minor_edits")
            self.assertEqual(payload["external_editor_publish_blockers_count"], 0)
            self.assertFalse(payload["external_editor_needs_revision"])
            self.assertTrue(payload["human_editor_required"])

    def test_discord_review_rejects_wrong_event_external_editor_decision(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path, draft_path = write_outputs(
                packet,
                packet_dir=root / "data" / "packets",
                draft_dir=root / "drafts" / "mystics",
            )
            _, decision_path = ingest_external_editor_response(
                packet,
                source_response_path=EXTERNAL_RESPONSE_FIXTURE,
                external_review_dir=root / "drafts" / "mystics" / "external_review",
            )
            decision_payload = json.loads(decision_path.read_text())
            decision_payload["event_id"] = "wrong-event"
            decision_path.write_text(json.dumps(decision_payload, indent=2, sort_keys=True) + "\n")

            with self.assertRaises(ValueError) as ctx:
                write_discord_review_package(
                    packet,
                    article_markdown_path=draft_path,
                    packet_path=packet_path,
                    review_dir=root / "drafts" / "mystics" / "review",
                )

            self.assertIn(str(decision_path), str(ctx.exception))
            self.assertIn("event_id 'wrong-event'", str(ctx.exception))
            self.assertIn("expected active packet event_id '401856918'", str(ctx.exception))

    def test_external_editor_packet_rejects_malformed_qa_report_from_disk(self) -> None:
        packet = build_postgame_packet(load_fixture_payload(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path, draft_path = write_outputs(
                packet,
                packet_dir=root / "data" / "packets",
                draft_dir=root / "drafts" / "mystics",
            )
            qa_path = write_editorial_qa_report(
                packet,
                article_markdown_path=draft_path,
                packet_path=packet_path,
                qa_dir=root / "drafts" / "mystics" / "qa",
            )
            qa_payload = json.loads(qa_path.read_text())
            qa_payload["advisory_only"] = False
            qa_path.write_text(json.dumps(qa_payload, indent=2, sort_keys=True) + "\n")

            with self.assertRaises(ValueError) as ctx:
                write_external_editor_review_packet(
                    packet,
                    article_markdown_path=draft_path,
                    external_review_dir=root / "drafts" / "mystics" / "external_review",
                    qa_report_path=qa_path,
                )

            self.assertIn(str(qa_path), str(ctx.exception))
            self.assertIn("Invalid QA report", str(ctx.exception))
            self.assertIn("advisory_only must be True", str(ctx.exception))

    def test_cli_discord_review_writes_review_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = main(
                [
                    "--fixture",
                    str(FIXTURE),
                    "--packet-dir",
                    str(root / "data" / "packets"),
                    "--draft-dir",
                    str(root / "drafts" / "mystics"),
                    "--discord-review",
                ]
            )

            review_path = root / "drafts" / "mystics" / "review" / "mystics-postgame-2026-05-19-401856918-review.json"
            self.assertEqual(result, 0)
            self.assertTrue(review_path.exists())
            payload = json.loads(review_path.read_text())
            self.assertIn("Mystics", payload["thread_title"])
            self.assertIn("2026-05-19", payload["thread_title"])
            self.assertIn("401856918", payload["thread_title"])

    def test_cli_qa_writes_report_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = main(
                [
                    "--fixture",
                    str(FIXTURE),
                    "--packet-dir",
                    str(root / "data" / "packets"),
                    "--draft-dir",
                    str(root / "drafts" / "mystics"),
                    "--qa",
                ]
            )

            qa_path = root / "drafts" / "mystics" / "qa" / "mystics-qa-401856918.json"
            self.assertEqual(result, 0)
            self.assertTrue(qa_path.exists())
            payload = json.loads(qa_path.read_text())
            self.assertEqual(set(payload["item_reports"]), {"main_article"})
            self.assertIn(payload["overall_recommendation"], QA_RECOMMENDATIONS)

    def test_cli_claim_audit_writes_audit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = main(
                [
                    "--fixture",
                    str(FIXTURE),
                    "--packet-dir",
                    str(root / "data" / "packets"),
                    "--draft-dir",
                    str(root / "drafts" / "mystics"),
                    "--claim-audit",
                ]
            )

            audit_path = root / "drafts" / "mystics" / "claim_audit" / "mystics-claim-audit-401856918.json"
            self.assertEqual(result, 0)
            self.assertTrue(audit_path.exists())
            payload = json.loads(audit_path.read_text())
            self.assertEqual(audit_path.name, "mystics-claim-audit-401856918.json")
            self.assertEqual(payload["schema_version"], "mystics-claim-evidence-audit/v0.2")
            self.assertEqual(payload["event_id"], "401856918")
            self.assertIn("sentence_map", payload)
            self.assertIn("sentence_summary", payload)
            self.assertIn("supported_by_packet", payload["summary"]["category_counts"])
            self.assertIs(schemas.validate_claim_evidence_audit(payload), payload)

    def test_cli_qa_with_generate_assets_scores_asset_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = main(
                [
                    "--fixture",
                    str(FIXTURE),
                    "--packet-dir",
                    str(root / "data" / "packets"),
                    "--draft-dir",
                    str(root / "drafts" / "mystics"),
                    "--generate-assets",
                    "--qa",
                ]
            )

            qa_path = root / "drafts" / "mystics" / "qa" / "mystics-qa-401856918.json"
            self.assertEqual(result, 0)
            payload = json.loads(qa_path.read_text())
            self.assertIn("short_recap", payload["item_reports"])
            self.assertIn("headline_candidates", payload["item_reports"])
            self.assertEqual(payload["summary"]["item_count"], 8)

    def test_cli_external_editor_packet_writes_review_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = main(
                [
                    "--fixture",
                    str(FIXTURE),
                    "--packet-dir",
                    str(root / "data" / "packets"),
                    "--draft-dir",
                    str(root / "drafts" / "mystics"),
                    "--generate-assets",
                    "--qa",
                    "--external-editor-packet",
                    "--discord-review",
                ]
            )

            external_path = (
                root
                / "drafts"
                / "mystics"
                / "external_review"
                / "mystics-external-review-401856918.json"
            )
            review_path = root / "drafts" / "mystics" / "review" / "mystics-postgame-2026-05-19-401856918-review.json"
            self.assertEqual(result, 0)
            self.assertTrue(external_path.exists())
            payload = json.loads(external_path.read_text())
            self.assertIn("short_recap", payload["generated_assets"])
            self.assertTrue(payload["internal_qa_summary"]["available"])
            self.assertIn("Return structured JSON only", payload["editor_prompt"])

            review_payload = json.loads(review_path.read_text())
            self.assertEqual(review_payload["external_editor_packet_path"], str(external_path))
            self.assertTrue(review_payload["recommended_external_review"])

    def test_cli_ingest_external_editor_response_writes_decision_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = main(
                [
                    "--fixture",
                    str(FIXTURE),
                    "--packet-dir",
                    str(root / "data" / "packets"),
                    "--draft-dir",
                    str(root / "drafts" / "mystics"),
                    "--ingest-external-editor-response",
                    str(EXTERNAL_RESPONSE_FIXTURE),
                    "--discord-review",
                ]
            )

            normalized_path = (
                root
                / "drafts"
                / "mystics"
                / "external_review"
                / "responses"
                / "mystics-external-editor-response-401856918.json"
            )
            decision_path = (
                root
                / "drafts"
                / "mystics"
                / "external_review"
                / "mystics-external-editor-decision-401856918.json"
            )
            review_path = root / "drafts" / "mystics" / "review" / "mystics-postgame-2026-05-19-401856918-review.json"
            self.assertEqual(result, 0)
            self.assertTrue(normalized_path.exists())
            self.assertTrue(decision_path.exists())
            decision = json.loads(decision_path.read_text())
            self.assertEqual(decision["overall_verdict"], "approve_with_minor_edits")
            self.assertTrue(decision["safe_to_publish_candidate"])
            self.assertTrue(decision["human_editor_required"])
            review = json.loads(review_path.read_text())
            self.assertEqual(review["external_editor_decision_path"], str(decision_path))
            self.assertEqual(review["external_editor_verdict"], "approve_with_minor_edits")

    def test_cli_ingest_external_editor_response_does_not_rewrite_existing_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft_dir = root / "drafts" / "mystics"
            draft_dir.mkdir(parents=True)
            draft_path = draft_dir / "mystics-postgame-2026-05-19-401856918.md"
            draft_path.write_text("existing human-reviewed draft\n")

            result = main(
                [
                    "--fixture",
                    str(FIXTURE),
                    "--packet-dir",
                    str(root / "data" / "packets"),
                    "--draft-dir",
                    str(draft_dir),
                    "--ingest-external-editor-response",
                    str(EXTERNAL_RESPONSE_FIXTURE),
                ]
            )

            self.assertEqual(result, 0)
            self.assertEqual(draft_path.read_text(), "existing human-reviewed draft\n")

    def test_cli_without_qa_does_not_write_qa_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = main(
                [
                    "--fixture",
                    str(FIXTURE),
                    "--packet-dir",
                    str(root / "data" / "packets"),
                    "--draft-dir",
                    str(root / "drafts" / "mystics"),
                ]
            )

            self.assertEqual(result, 0)
            self.assertFalse((root / "drafts" / "mystics" / "qa").exists())

    def test_cli_without_claim_audit_does_not_write_audit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = main(
                [
                    "--fixture",
                    str(FIXTURE),
                    "--packet-dir",
                    str(root / "data" / "packets"),
                    "--draft-dir",
                    str(root / "drafts" / "mystics"),
                ]
            )

            self.assertEqual(result, 0)
            self.assertFalse((root / "drafts" / "mystics" / "claim_audit").exists())

    def test_cli_generate_assets_writes_asset_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = main(
                [
                    "--fixture",
                    str(FIXTURE),
                    "--packet-dir",
                    str(root / "data" / "packets"),
                    "--draft-dir",
                    str(root / "drafts" / "mystics"),
                    "--generate-assets",
                ]
            )

            asset_dir = root / "drafts" / "mystics" / "assets"
            index_path = asset_dir / "mystics-assets-index-401856918.json"
            self.assertEqual(result, 0)
            self.assertTrue(index_path.exists())
            index = json.loads(index_path.read_text())
            self.assertEqual(len(index["generated_asset_paths"]), 7)
            self.assertIn("push_alert", index["generated_asset_paths"])


if __name__ == "__main__":
    unittest.main()
