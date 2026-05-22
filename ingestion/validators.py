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
        if "published_at" in item and not _is_utc_iso(item.get("published_at")):
            errors.append(f"recent_news_items[{i}].published_at must be ISO 8601 UTC")
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

    if errors:
        raise ValueError("Invalid story packet:\n- " + "\n- ".join(errors))
    return packet

