"""Story packet schema types.

These TypedDicts intentionally mirror generate_content.consume_story_packet().
They are runtime-light so the ingestion MVP can run with the pipeline's current
standard-library-plus-requests dependency set.
"""

from __future__ import annotations

from typing import Literal, TypedDict


EventType = Literal[
    "game",
    "news",
    "injury",
    "transaction",
    "standings_update",
    "off_day",
]


class GameSummary(TypedDict, total=False):
    score: str
    venue: str
    opponent: str
    date: str
    status: str
    home_away: str


class TopPerformer(TypedDict):
    player: str
    stat_line: str
    note: str


class KeyPlayer(TypedDict):
    name: str
    role: str


class Availability(TypedDict):
    player: str
    status: str
    note: str
    source_url: str


class NewsItem(TypedDict):
    title: str
    url: str
    published_at: str
    source_name: str
    confidence: float


class SourceLink(TypedDict):
    source_name: str
    source_url: str
    published_at: str
    retrieved_at: str
    confidence: float


class StoryPacket(TypedDict):
    team: str
    league: str
    event_type: EventType
    retrieved_at: str
    kb_slug: str
    game_summary: GameSummary | None
    top_performers: list[TopPerformer]
    recent_team_context: str
    key_players: list[KeyPlayer]
    injuries_or_availability: list[Availability]
    standings_context: str
    recent_news_items: list[NewsItem]
    editorial_angle_candidates: list[str]
    confidence_notes: list[str]
    source_links: list[SourceLink]


REQUIRED_PACKET_FIELDS = tuple(StoryPacket.__annotations__.keys())

