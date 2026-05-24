"""Tests for the production packet path: build_story_packet_for_team + espn_generic.

The original tests/test_story_packet.py only covers build_story_packet (the
deprecated Mystics-only path). These tests cover the function CI actually
invokes from .github/workflows/daily-content.yml and that generate_content.py
consumes at runtime.

ESPN HTTP calls are patched at ingestion.fetchers.espn_generic.fetch so the
tests don't hit the network and are deterministic against ESPN shape drift.
The team KB file (data/teams/commanders.json) is read for real — that lets
the test catch breakage if the KB shape and the packet builder diverge.
"""
from __future__ import annotations

import sys
import types
import unittest
from datetime import date
from unittest import mock

try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    sys.modules["requests"] = types.SimpleNamespace()

from generate_content import consume_story_packet
from ingestion.fetchers import espn_generic
from ingestion.generate_story_packet import build_story_packet_for_team
from ingestion.validators import validate_packet


RETRIEVED_AT = "2026-05-23T14:30:00Z"
TARGET_DATE = date(2026, 1, 4)   # the Commanders' Eagles game


def _source(name: str, url: str) -> dict[str, object]:
    return {
        "source_name": name,
        "source_url": url,
        "published_at": "2026-01-04T00:00:00Z",
        "retrieved_at": RETRIEVED_AT,
        "confidence": 0.9,
    }


def _game_day_espn_fetch(**_kwargs) -> dict[str, object]:
    """Stand-in for espn_generic.fetch — emits the shape build_story_packet_for_team
    expects: game_summary, top_performers, recent_team_context, boxscore.entries,
    source_links, confidence_notes."""
    return {
        "game_summary": {
            "score": "Washington Commanders 24, Philadelphia Eagles 17",
            "venue": "Lincoln Financial Field",
            "opponent": "Philadelphia Eagles",
            "date": "2026-01-04T18:00:00Z",
            "status": "Final",
            "home_away": "away",
        },
        "top_performers": [
            {"player": "Jayden Daniels", "stat_line": "26/32, 287 yds, 2 TD", "note": "ESPN boxscore (Commanders)"}
        ],
        "recent_team_context": "Closed the 2025 season with a road win in Philadelphia.",
        "editorial_angle_candidates": [],
        "boxscore": {
            "team_name": "Washington Commanders",
            "team_abbr": "WSH",
            "home_away": "away",
            "sport": "football",
            "league": "nfl",
            "entries": [
                {
                    "player": "Jayden Daniels",
                    "position": "QB",
                    "starter": True,
                    "section": "passing",
                    "stats": {"C/ATT": "26/32", "YDS": "287", "TD": "2", "INT": "0"},
                }
            ],
        },
        "opponent_boxscore": None,
        "source_links": [_source("ESPN NFL summary", "https://example.test/espn/summary")],
        "confidence_notes": [],
    }


def _off_day_espn_fetch(**_kwargs) -> dict[str, object]:
    return {
        "game_summary": None,
        "top_performers": [],
        "recent_team_context": "",
        "editorial_angle_candidates": [],
        "boxscore": None,
        "opponent_boxscore": None,
        "source_links": [_source("ESPN NFL scoreboard", "https://example.test/espn/scoreboard")],
        "confidence_notes": [],
    }


class BuildStoryPacketForTeamTests(unittest.TestCase):
    def test_game_day_round_trip_validates_and_consumes(self) -> None:
        with mock.patch.object(espn_generic, "fetch", side_effect=_game_day_espn_fetch):
            packet = build_story_packet_for_team(
                "commanders", TARGET_DATE, retrieved_at=RETRIEVED_AT
            )

        validate_packet(packet)
        rendered = consume_story_packet(packet)

        self.assertEqual(packet["team"], "Washington Commanders")
        self.assertEqual(packet["league"], "NFL")
        self.assertEqual(packet["event_type"], "game")
        self.assertIn("Jayden Daniels", rendered)
        # boxscore in the new sport-neutral entries shape survives the round trip
        self.assertIn("entries", packet["boxscore"])
        self.assertEqual(packet["boxscore"]["entries"][0]["player"], "Jayden Daniels")

    def test_off_day_marks_event_type_and_adds_confidence_note(self) -> None:
        with mock.patch.object(espn_generic, "fetch", side_effect=_off_day_espn_fetch):
            packet = build_story_packet_for_team(
                "commanders", TARGET_DATE, retrieved_at=RETRIEVED_AT
            )

        validate_packet(packet)
        self.assertEqual(packet["event_type"], "off_day")
        self.assertIsNone(packet["game_summary"])
        self.assertTrue(any("no game played on" in n for n in packet["confidence_notes"]))

    def test_unknown_team_slug_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            build_story_packet_for_team("not-a-real-team", TARGET_DATE)
        self.assertIn("Unknown team slug", str(ctx.exception))


class EspnGenericInternalsTests(unittest.TestCase):
    """Pure-Python unit tests for espn_generic helpers — no network."""

    def test_find_team_game_matches_by_id(self) -> None:
        events = [
            {
                "id": "1",
                "competitions": [
                    {"competitors": [
                        {"team": {"id": "99", "displayName": "Other Team"}},
                        {"team": {"id": "28", "displayName": "Washington Commanders"}},
                    ]},
                ],
            },
        ]
        event = espn_generic._find_team_game(events, "28", "Washington Commanders")
        self.assertIsNotNone(event)
        self.assertEqual(event["id"], "1")

    def test_find_team_game_matches_by_display_name_when_id_missing(self) -> None:
        events = [
            {
                "id": "2",
                "competitions": [
                    {"competitors": [
                        {"team": {"id": "", "displayName": "Washington Commanders"}},
                    ]},
                ],
            },
        ]
        event = espn_generic._find_team_game(events, "999999", "Washington Commanders")
        self.assertIsNotNone(event)
        self.assertEqual(event["id"], "2")

    def test_find_team_game_returns_none_when_no_match(self) -> None:
        events = [
            {
                "id": "3",
                "competitions": [
                    {"competitors": [{"team": {"id": "1", "displayName": "Other"}}]},
                ],
            },
        ]
        self.assertIsNone(espn_generic._find_team_game(events, "28", "Washington Commanders"))


if __name__ == "__main__":
    unittest.main()
