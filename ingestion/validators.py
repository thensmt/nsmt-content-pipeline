"""Runtime validation for story packets."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .schema import REQUIRED_PACKET_FIELDS


EVENT_TYPES = {
    "game",
    "news",
    "injury",
    "transaction",
    "standings_update",
    "off_day",
}


def _is_utc_iso(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def _require_keys(name: str, item: dict[str, Any], keys: tuple[str, ...], errors: list[str]) -> None:
    for key in keys:
        if key not in item:
            errors.append(f"{name} missing required key: {key}")


def _validate_confidence(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, (float, int)) or isinstance(value, bool):
        errors.append(f"{path} must be a float 0.0-1.0")
        return
    if value < 0.0 or value > 1.0:
        errors.append(f"{path} must be between 0.0 and 1.0")


def validate_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Validate the public story packet contract.

    Returns the original packet for convenient call chaining. Raises ValueError
    with all discovered schema issues.
    """
    errors: list[str] = []

    if not isinstance(packet, dict):
        raise ValueError("story packet must be a dict")

    for field in REQUIRED_PACKET_FIELDS:
        if field not in packet:
            errors.append(f"missing required field: {field}")

    if packet.get("event_type") not in EVENT_TYPES:
        errors.append("event_type must be one of the controlled vocabulary values")

    if not _is_utc_iso(packet.get("retrieved_at")):
        errors.append("retrieved_at must be ISO 8601 UTC ending in Z")

    for field in ("team", "league", "kb_slug", "recent_team_context", "standings_context"):
        if field in packet and not isinstance(packet[field], str):
            errors.append(f"{field} must be a string")

    if packet.get("game_summary") is not None and not isinstance(packet.get("game_summary"), dict):
        errors.append("game_summary must be a dict or null")

    list_fields = (
        "top_performers",
        "key_players",
        "injuries_or_availability",
        "recent_news_items",
        "editorial_angle_candidates",
        "confidence_notes",
        "source_links",
    )
    for field in list_fields:
        if field in packet and not isinstance(packet[field], list):
            errors.append(f"{field} must be a list")

    for i, item in enumerate(packet.get("top_performers") or []):
        if isinstance(item, dict):
            _require_keys(f"top_performers[{i}]", item, ("player", "stat_line", "note"), errors)
        else:
            errors.append(f"top_performers[{i}] must be a dict")

    for i, item in enumerate(packet.get("key_players") or []):
        if isinstance(item, dict):
            _require_keys(f"key_players[{i}]", item, ("name", "role"), errors)
        else:
            errors.append(f"key_players[{i}] must be a dict")

    for i, item in enumerate(packet.get("injuries_or_availability") or []):
        if isinstance(item, dict):
            _require_keys(
                f"injuries_or_availability[{i}]",
                item,
                ("player", "status", "note", "source_url"),
                errors,
            )
        else:
            errors.append(f"injuries_or_availability[{i}] must be a dict")

    for i, item in enumerate(packet.get("recent_news_items") or []):
        if not isinstance(item, dict):
            errors.append(f"recent_news_items[{i}] must be a dict")
            continue
        _require_keys(
            f"recent_news_items[{i}]",
            item,
            ("title", "url", "published_at", "source_name", "confidence"),
            errors,
        )
        if "published_at" in item:
            value = item.get("published_at")
            if value is not None and not _is_utc_iso(value):
                errors.append(f"recent_news_items[{i}].published_at must be ISO 8601 UTC or null")
        if "confidence" in item:
            _validate_confidence(item.get("confidence"), f"recent_news_items[{i}].confidence", errors)

    for i, item in enumerate(packet.get("source_links") or []):
        if not isinstance(item, dict):
            errors.append(f"source_links[{i}] must be a dict")
            continue
        _require_keys(
            f"source_links[{i}]",
            item,
            ("source_name", "source_url", "published_at", "retrieved_at", "confidence"),
            errors,
        )
        for timestamp_key in ("published_at", "retrieved_at"):
            if timestamp_key in item and not _is_utc_iso(item.get(timestamp_key)):
                errors.append(f"source_links[{i}].{timestamp_key} must be ISO 8601 UTC")
        if "confidence" in item:
            _validate_confidence(item.get("confidence"), f"source_links[{i}].confidence", errors)

    for field in ("editorial_angle_candidates", "confidence_notes"):
        for i, item in enumerate(packet.get(field) or []):
            if not isinstance(item, str):
                errors.append(f"{field}[{i}] must be a string")

    for field in ("boxscore", "opponent_boxscore"):
        if field in packet and packet.get(field) is not None:
            _validate_boxscore(field, packet[field], errors)

    if errors:
        raise ValueError("Invalid story packet:\n- " + "\n- ".join(errors))
    return packet


# ── Boxscore validation ───────────────────────────────────────────────────────
#
# The boxscore fields are optional but, when present, are injected into the
# writer prompt as authoritative source material the model is told to trust
# verbatim. So if a fetcher emits malformed structure (ESPN shape change,
# bad regex, etc.) we want to fail fast — better to lose the packet than
# pass bogus stats through to the writer.

_BOXSCORE_OPTIONAL_STR_KEYS = ("team_name", "team_abbr", "home_away", "sport", "league")


def _validate_boxscore(path: str, boxscore: Any, errors: list[str]) -> None:
    if not isinstance(boxscore, dict):
        errors.append(f"{path} must be a dict or null")
        return

    for key in _BOXSCORE_OPTIONAL_STR_KEYS:
        if key in boxscore and not isinstance(boxscore[key], str):
            errors.append(f"{path}.{key} must be a string")

    has_rows = "rows" in boxscore and boxscore["rows"] is not None
    has_entries = "entries" in boxscore and boxscore["entries"] is not None
    if has_rows and has_entries:
        errors.append(f"{path}: rows and entries are mutually exclusive (got both)")
    if not has_rows and not has_entries:
        errors.append(f"{path}: must have either rows or entries (got neither)")

    if has_rows:
        if not isinstance(boxscore["rows"], list):
            errors.append(f"{path}.rows must be a list")
        else:
            for i, row in enumerate(boxscore["rows"]):
                if not isinstance(row, dict):
                    errors.append(f"{path}.rows[{i}] must be a dict")
                    continue
                if "player" not in row or not isinstance(row.get("player"), str) or not row["player"].strip():
                    errors.append(f"{path}.rows[{i}].player must be a non-empty string")

    if has_entries:
        if not isinstance(boxscore["entries"], list):
            errors.append(f"{path}.entries must be a list")
        else:
            for i, entry in enumerate(boxscore["entries"]):
                if not isinstance(entry, dict):
                    errors.append(f"{path}.entries[{i}] must be a dict")
                    continue
                if "player" not in entry or not isinstance(entry.get("player"), str) or not entry["player"].strip():
                    errors.append(f"{path}.entries[{i}].player must be a non-empty string")
                if "stats" in entry:
                    stats = entry.get("stats")
                    if not isinstance(stats, dict):
                        errors.append(f"{path}.entries[{i}].stats must be a dict")
                    else:
                        for stat_key, stat_val in stats.items():
                            if not isinstance(stat_key, str) or not stat_key.strip():
                                errors.append(f"{path}.entries[{i}].stats has a non-string label")
                            if not isinstance(stat_val, str):
                                errors.append(f"{path}.entries[{i}].stats[{stat_key!r}] must be a string")

