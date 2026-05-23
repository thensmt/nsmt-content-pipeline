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
    linescore: str
    attendance: int


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
    published_at: str | None
    source_name: str
    confidence: float


class SourceLink(TypedDict):
    source_name: str
    source_url: str
    published_at: str
    retrieved_at: str
    confidence: float


# Per-player stat row from a basketball boxscore — the original shape, kept
# for backwards compatibility with the Mystics packet path. New sports use
# BoxscoreEntry (below) instead, which is sport-agnostic.
class BoxscoreRow(TypedDict, total=False):
    player: str
    position: str
    minutes: str
    points: int
    rebounds: int
    assists: int
    steals: int
    blocks: int
    turnovers: int
    fg: str           # e.g. "10-14"
    three_pt: str     # e.g. "1-4"
    ft: str           # e.g. "9-10"
    plus_minus: int
    starter: bool


# Sport-agnostic per-player line. `stats` holds whatever labels ESPN returns
# for this section in this sport — e.g. for MLB batting: H-AB / AB / R / H /
# RBI / HR / BB / K / AVG / OBP / SLG; for MLB pitching: IP / H / R / ER /
# BB / K / ERA; for basketball: MIN / PTS / REB / AST / FG / 3P / FT / +/-.
# Renderer iterates and prints the labels as-given — no per-sport hardcoding
# required to add a new league.
class BoxscoreEntry(TypedDict, total=False):
    player: str
    position: str
    starter: bool
    section: str                  # 'batting', 'pitching', 'players', 'skaters', 'goaltenders', etc.
    stats: dict[str, str]


class TeamBoxscore(TypedDict, total=False):
    team_name: str
    team_abbr: str
    home_away: str
    sport: str                    # 'basketball', 'baseball', 'football', 'hockey', 'soccer'
    league: str                   # 'WNBA', 'MLB', 'NFL', 'NHL', etc.
    # Either `rows` (legacy basketball-shaped) OR `entries` (new sport-
    # neutral) will be populated, never both. Renderer checks both and
    # prefers entries when present.
    rows: list[BoxscoreRow]
    entries: list[BoxscoreEntry]


class StoryPacket(TypedDict, total=False):
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
    # Optional — present when we successfully pulled ESPN summary for the
    # recapped game. The writer + fact-checker MUST prefer these per-player
    # numbers over training-data recall.
    boxscore: TeamBoxscore | None
    opponent_boxscore: TeamBoxscore | None


# The original required set — kept explicit so adding optional fields above
# doesn't suddenly break older callers / writers / tests.
REQUIRED_PACKET_FIELDS = (
    "team",
    "league",
    "event_type",
    "retrieved_at",
    "kb_slug",
    "game_summary",
    "top_performers",
    "recent_team_context",
    "key_players",
    "injuries_or_availability",
    "standings_context",
    "recent_news_items",
    "editorial_angle_candidates",
    "confidence_notes",
    "source_links",
)

