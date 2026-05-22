"""Washington Mystics official site news fetcher."""

from __future__ import annotations

import html
import logging
import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

from ingestion.cache import OFFICIAL_SITE_TTL_MIN, SourceFetchError, date_to_utc_iso, get_cached_json, request_text


logger = logging.getLogger(__name__)

NEWS_URL = "https://mystics.wnba.com/news"
SOURCE_NAME = "Washington Mystics official site"
SKIP_TITLES = {
    "home",
    "schedule",
    "tickets",
    "roster",
    "news",
    "game notes",
    "ticket",
    "shop",
    "league pass",
    "wnba",
    "privacy policy",
    "terms of use",
    "washington mystics",
}


def fetch(target_date: date, retrieved_at: str) -> dict[str, Any]:
    try:
        html_text = get_cached_json(
            "mystics_official",
            f"news_{target_date.isoformat()}",
            OFFICIAL_SITE_TTL_MIN,
            lambda: {"html": request_text(NEWS_URL)},
        ).get("html", "")
    except (AttributeError, SourceFetchError, ValueError) as exc:
        logger.warning("Mystics official site fetch failed: %s", exc)
        return {
            "recent_news_items": [],
            "source_links": [],
            "confidence_notes": [f"Washington Mystics official news unavailable: {exc}"],
        }

    items = _parse_news(html_text)
    source = {
        "source_name": SOURCE_NAME,
        "source_url": NEWS_URL,
        "published_at": date_to_utc_iso(target_date.isoformat()),
        "retrieved_at": retrieved_at,
        "confidence": 0.82 if items else 0.55,
    }
    notes = [] if items else ["Washington Mystics official news page fetched but no story links were parsed"]
    return {"recent_news_items": items, "source_links": [source], "confidence_notes": notes}


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._href:
            return
        title = re.sub(r"\s+", " ", " ".join(self._parts)).strip()
        if title:
            self.links.append({"title": html.unescape(title), "href": self._href})
        self._href = None
        self._parts = []


def _parse_news(html_text: str) -> list[dict[str, Any]]:
    parser = _LinkParser()
    parser.feed(html_text)
    visible = _visible_text(html_text)

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in parser.links:
        title = link["title"].strip()
        title_key = title.lower()
        href = urljoin(NEWS_URL, link["href"])
        if title_key in SKIP_TITLES or len(title) < 12:
            continue
        if "mystics.wnba.com" not in href or "/news" not in href:
            continue
        if href in seen:
            continue
        seen.add(href)
        items.append(
            {
                "title": title,
                "url": href,
                "published_at": _published_at_for_title(visible, title),
                "source_name": SOURCE_NAME,
                "confidence": 0.82,
            }
        )
        if len(items) >= 5:
            break
    return items


def _published_at_for_title(text: str, title: str) -> str | None:
    idx = text.find(title)
    if idx < 0:
        return None
    window = text[idx : idx + 300]
    match = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+\d{4}",
        window,
        re.IGNORECASE,
    )
    if not match:
        return None
    raw = match.group(0).replace(".", "")
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return date_to_utc_iso(parsed.date().isoformat())
        except ValueError:
            continue
    return None


def _visible_text(html_text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html_text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text)

