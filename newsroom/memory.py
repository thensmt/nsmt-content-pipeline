"""Mystics editorial memory loading and summaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from newsroom.common import DEFAULT_MEMORY_DIR

MEMORY_FILES = {
    "season_narratives": "season_narratives.json",
    "player_profiles": "player_profiles.json",
    "recent_storylines": "recent_storylines.json",
    "editorial_rules": "editorial_rules.json",
}

def load_mystics_memory(memory_dir: Path | str | None = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    """Load persistent Mystics memory files without making them hard dependencies."""
    root = Path(memory_dir) if memory_dir is not None else DEFAULT_MEMORY_DIR
    memory: dict[str, Any] = {
        "memory_dir": str(root),
        "missing_files": [],
        "load_errors": [],
    }
    for key, filename in MEMORY_FILES.items():
        path = root / filename
        if not path.exists():
            memory[key] = {}
            memory["missing_files"].append(filename)
            continue
        try:
            memory[key] = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            memory[key] = {}
            memory["load_errors"].append(f"{filename}: {exc}")
    return memory


def _external_memory_context_summary(packet: dict[str, Any]) -> dict[str, Any]:
    memory = packet.get("memory") or {}
    return {
        "memory_dir": memory.get("memory_dir"),
        "missing_files": memory.get("missing_files") or [],
        "load_errors": memory.get("load_errors") or [],
        "season_narratives": [
            {
                "id": item.get("id"),
                "label": item.get("label"),
                "context": item.get("context"),
                "risk_flags": item.get("risk_flags") or [],
            }
            for item in ((memory.get("season_narratives") or {}).get("narratives") or [])
            if isinstance(item, dict)
        ],
        "recent_storylines": [
            {
                "id": item.get("id"),
                "label": item.get("label"),
                "context": item.get("context"),
                "risk_flags": item.get("risk_flags") or [],
            }
            for item in ((memory.get("recent_storylines") or {}).get("storylines") or [])
            if isinstance(item, dict)
        ],
        "player_profile_lenses": [
            {
                "player": item.get("player"),
                "editorial_lens": item.get("editorial_lens"),
                "avoid": item.get("avoid") or [],
            }
            for item in ((memory.get("player_profiles") or {}).get("profiles") or [])
            if isinstance(item, dict)
        ],
        "default_risk_flags": (memory.get("editorial_rules") or {}).get("default_risk_flags") or [],
    }


def _memory_item(memory: dict[str, Any], section: str, collection: str, item_id: str) -> dict[str, Any]:
    for item in ((memory.get(section) or {}).get(collection) or []):
        if isinstance(item, dict) and item.get("id") == item_id:
            return item
    return {}


def _player_profile(memory: dict[str, Any], player_name: str) -> dict[str, Any]:
    for item in ((memory.get("player_profiles") or {}).get("profiles") or []):
        if isinstance(item, dict) and item.get("player") == player_name:
            return item
    return {}


def _default_memory_risk_flags(memory: dict[str, Any]) -> list[str]:
    flags = list((memory.get("editorial_rules") or {}).get("default_risk_flags") or [])
    if memory.get("missing_files"):
        flags.append(f"Missing memory files: {', '.join(memory['missing_files'])}.")
    if memory.get("load_errors"):
        flags.append(f"Memory load errors: {'; '.join(memory['load_errors'])}.")
    return flags
