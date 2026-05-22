from __future__ import annotations

import unittest
import sys
import types
from datetime import date

try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    sys.modules["requests"] = types.SimpleNamespace()

from generate_content import consume_story_packet
from ingestion.generate_story_packet import build_story_packet
from ingestion.validators import validate_packet


RETRIEVED_AT = "2026-05-22T14:30:00Z"


def _source(name: str, url: str) -> dict[str, object]:
    return {
        "source_name": name,
        "source_url": url,
        "published_at": "2026-05-21T00:00:00Z",
        "retrieved_at": RETRIEVED_AT,
        "confidence": 0.9,
    }


def _game_fetcher(target_date: date, retrieved_at: str) -> dict[str, object]:
    return {
        "game_summary": {
            "score": "Washington Mystics 82, Test Opponent 75",
            "venue": "CareFirst Arena",
            "opponent": "Test Opponent",
            "date": "2026-05-21T23:30:00Z",
            "status": "Final",
        },
        "top_performers": [
            {"player": "Shakira Austin", "stat_line": "20 pts, 8 reb", "note": "fixture leader"}
        ],
        "recent_team_context": "Fixture ESPN context.",
        "source_links": [_source("ESPN WNBA scoreboard", "https://example.test/espn")],
        "confidence_notes": [],
    }


def _off_day_fetcher(target_date: date, retrieved_at: str) -> dict[str, object]:
    return {
        "game_summary": None,
        "top_performers": [],
        "recent_team_context": "",
        "source_links": [_source("ESPN WNBA scoreboard", "https://example.test/espn")],
        "confidence_notes": [],
    }


def _wnba_fetcher(target_date: date, retrieved_at: str) -> dict[str, object]:
    return {
        "standings_context": "WNBA.com lists Washington at 2-2, rank 9 overall.",
        "injuries_or_availability": [
            {
                "player": "Fixture Player",
                "status": "Questionable",
                "note": "Fixture availability note",
                "source_url": "https://example.test/injury",
            }
        ],
        "source_links": [_source("WNBA.com standings", "https://example.test/standings")],
        "confidence_notes": [],
    }


def _official_fetcher(target_date: date, retrieved_at: str) -> dict[str, object]:
    return {
        "recent_news_items": [
            {
                "title": "Mystics Fixture News Item",
                "url": "https://example.test/news",
                "published_at": "2026-05-21T00:00:00Z",
                "source_name": "Washington Mystics official site",
                "confidence": 0.82,
            }
        ],
        "source_links": [_source("Washington Mystics official site", "https://example.test/news")],
        "confidence_notes": [],
    }


def _reddit_stub(target_date: date, retrieved_at: str) -> list[dict[str, object]]:
    return []


class StoryPacketTests(unittest.TestCase):
    def test_schema_round_trip_consumes_to_prompt_block(self) -> None:
        packet = build_story_packet(
            "mystics",
            date(2026, 5, 21),
            retrieved_at=RETRIEVED_AT,
            fetchers={
                "espn": _game_fetcher,
                "wnba_com": _wnba_fetcher,
                "mystics_official": _official_fetcher,
                "reddit": _reddit_stub,
            },
        )

        validate_packet(packet)
        rendered = consume_story_packet(packet)

        self.assertEqual(packet["event_type"], "game")
        self.assertIsInstance(rendered, str)
        self.assertIn("Story packet", rendered)
        self.assertIn("Mystics Fixture News Item", rendered)

    def test_off_day_fallback_keeps_news_and_standings(self) -> None:
        packet = build_story_packet(
            "mystics",
            date(2026, 5, 21),
            retrieved_at=RETRIEVED_AT,
            fetchers={
                "espn": _off_day_fetcher,
                "wnba_com": _wnba_fetcher,
                "mystics_official": _official_fetcher,
                "reddit": _reddit_stub,
            },
        )

        self.assertEqual(packet["event_type"], "off_day")
        self.assertIsNone(packet["game_summary"])
        self.assertEqual(len(packet["recent_news_items"]), 1)
        self.assertIn("Washington at 2-2", packet["standings_context"])
        self.assertIn("no game played on 2026-05-21", packet["confidence_notes"])


if __name__ == "__main__":
    unittest.main()
