"""Reddit source stub for r/washingtonmystics.

The interface is intentionally present for future extension, but the MVP does
not fetch Reddit. TODO: wire a read-only public JSON/API path after review of
rate limits, moderation risks, and attribution rules.
"""

from __future__ import annotations

from datetime import date
from typing import Any


def fetch(target_date: date, retrieved_at: str, *, enabled: bool = False) -> list[dict[str, Any]]:
    if enabled:
        raise NotImplementedError(
            "Reddit ingestion is stubbed for the MVP; implement r/washingtonmystics fetching later."
        )
    return []

