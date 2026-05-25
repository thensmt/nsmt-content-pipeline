"""Shared constants and helpers for the Mystics postgame MVP."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SPORT = "basketball"
LEAGUE_SLUG = "wnba"
LEAGUE = "WNBA"
TEAM_ID = "16"
TEAM_NAME = "Washington Mystics"
TEAM_ABBR = "WSH"

DEFAULT_PACKET_DIR = PROJECT_ROOT / "data" / "packets"
DEFAULT_DRAFT_DIR = PROJECT_ROOT / "drafts" / "mystics"
DEFAULT_REVIEW_DIR = DEFAULT_DRAFT_DIR / "review"
DEFAULT_ASSET_DIR = DEFAULT_DRAFT_DIR / "assets"
DEFAULT_QA_DIR = DEFAULT_DRAFT_DIR / "qa"
DEFAULT_CLAIM_AUDIT_DIR = DEFAULT_DRAFT_DIR / "claim_audit"
DEFAULT_EXTERNAL_REVIEW_DIR = DEFAULT_DRAFT_DIR / "external_review"
DEFAULT_EXTERNAL_RESPONSE_DIR = DEFAULT_EXTERNAL_REVIEW_DIR / "responses"
DEFAULT_WRITER_PROFILE = PROJECT_ROOT / "data" / "writers" / "maya-brooks.json"
DEFAULT_MEMORY_DIR = PROJECT_ROOT / "data" / "memory" / "mystics"
EXTERNAL_EDITOR_PROMPT_PATH = PROJECT_ROOT / "prompts" / "editors" / "claude_external_editor.md"

MAYA_BROOKS_PROFILE: dict[str, Any] = {
    "id": "maya-brooks",
    "name": "Maya Brooks",
    "title": "Washington Mystics AI beat writer",
    "publication": "NSMT",
    "beat": "Washington Mystics",
    "league": "WNBA",
    "voice": (
        "clear, observant, and basketball-literate; explains game flow through "
        "lineups, possessions, and pressure points without turning the recap "
        "into a spreadsheet"
    ),
    "focus_areas": [
        "guard play and half-court creation",
        "frontcourt rebounding and paint touches",
        "bench minutes that change game texture",
        "late-quarter runs and turnover swings",
    ],
    "guardrails": [
        "Use only normalized ESPN packet facts for scores, stats, and play sequence.",
        "Do not call a stat a season high, career high, or first since unless the packet says so.",
        "Flag unavailable data instead of filling gaps from memory.",
        "Keep AI disclosure in metadata/byline, not in the article body.",
    ],
}

def _display_path(path: Path | str) -> str:
    path_obj = Path(path)
    try:
        return str(path_obj.resolve().relative_to(PROJECT_ROOT))
    except (OSError, ValueError):
        return str(path)


def _parse_espn_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    match = re.search(r"-?\d+", str(value))
    if not match:
        return None
    return int(match.group(0))


def _team_by_id(teams: list[dict[str, Any]], team_id: str) -> dict[str, Any]:
    for team in teams:
        if str(team.get("id")) == str(team_id):
            return team
    raise ValueError(f"Team id {team_id} not present in normalized game")


def _opponent_team(teams: list[dict[str, Any]]) -> dict[str, Any]:
    for team in teams:
        if str(team.get("id")) != TEAM_ID:
            return team
    raise ValueError("Opponent not present in normalized game")


def _display_date(value: Any) -> str:
    dt = _parse_espn_datetime(value)
    if not dt:
        return str(value or "the listed date")
    return dt.strftime("%B %-d, %Y") if sys.platform != "win32" else dt.strftime("%B %#d, %Y")


def _word_count(text: Any) -> int:
    return len(re.findall(r"\b[\w'-]+\b", str(text or "")))


def _dedupe_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip() and value.strip() not in out:
            out.append(value.strip())
    return out


def _confidence(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 2)


def _selected_angle(packet: dict[str, Any]) -> dict[str, Any]:
    angles = packet.get("story_angles") or []
    return angles[0] if angles else {}


def _editorial_rules(packet: dict[str, Any]) -> list[str]:
    rules = ((packet.get("memory") or {}).get("editorial_rules") or {}).get("rules") or []
    return [str(rule) for rule in rules if str(rule).strip()]


def _load_writer_profile() -> dict[str, Any]:
    if DEFAULT_WRITER_PROFILE.exists():
        return json.loads(DEFAULT_WRITER_PROFILE.read_text())
    return MAYA_BROOKS_PROFILE


def _load_assets_from_paths(asset_paths: dict[str, Path | str]) -> dict[str, Any]:
    assets: dict[str, Any] = {}
    for item_key, path in asset_paths.items():
        path_obj = Path(path)
        if not path_obj.exists():
            continue
        if item_key == "headline_candidates":
            try:
                assets[item_key] = json.loads(path_obj.read_text())
            except json.JSONDecodeError:
                assets[item_key] = path_obj.read_text()
        else:
            assets[item_key] = path_obj.read_text()
    return assets


def _review_top_performers(performers: list[dict[str, Any]], limit: int = 4) -> str:
    rows = []
    for performer in performers[:limit]:
        player = performer.get("player") or "Unknown player"
        team = performer.get("team") or "Unknown team"
        stat_line = performer.get("stat_line") or "stat line unavailable"
        rows.append(f"{player} ({team}) - {stat_line}")
    return "; ".join(rows)


def _risk_summary(risk_flags: list[str], limit: int = 4) -> str:
    return "; ".join(risk_flags[:limit]) if risk_flags else "None flagged."
