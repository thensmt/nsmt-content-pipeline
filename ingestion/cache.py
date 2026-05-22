"""JSON cache and HTTP helpers for ingestion fetchers."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.robotparser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - exercised only in minimal local envs
    requests = None


ESPN_TTL_MIN = 15
WNBA_NEWS_TTL_MIN = 120
OFFICIAL_SITE_TTL_MIN = 60

USER_AGENT = "NSMT-StoryPacket/0.1 (+https://thensmt.com)"
CACHE_ROOT = Path("cache")

logger = logging.getLogger(__name__)

_LAST_REQUEST_AT: dict[str, float] = {}
_ROBOTS_CACHE: dict[str, urllib.robotparser.RobotFileParser] = {}


class SourceFetchError(RuntimeError):
    """Raised when a source cannot be fetched safely."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(dt: datetime | None = None) -> str:
    dt = dt or utc_now()
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def date_to_utc_iso(value: str) -> str:
    return f"{value}T00:00:00Z"


def cache_key(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe.strip("_") or "default"


def get_cached_json(
    source_name: str,
    key: str,
    ttl_minutes: int,
    fetch: Callable[[], Any],
) -> Any:
    """Return cached JSON data within TTL, otherwise fetch and persist."""
    cache_path = CACHE_ROOT / source_name / f"{cache_key(key)}.json"
    now = utc_now()

    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text())
            cached_at = datetime.fromisoformat(cached["cached_at"].replace("Z", "+00:00"))
            if now - cached_at <= timedelta(minutes=ttl_minutes):
                return cached.get("data")
        except (KeyError, ValueError, json.JSONDecodeError, OSError) as exc:
            logger.warning("Ignoring invalid cache entry %s: %s", cache_path, exc)

    data = fetch()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"cached_at": iso_utc(now), "data": data}, indent=2, sort_keys=True) + "\n"
    )
    return data


def _robots_for(url: str) -> urllib.robotparser.RobotFileParser:
    parsed = urllib.parse.urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    if base in _ROBOTS_CACHE:
        return _ROBOTS_CACHE[base]

    robots = urllib.robotparser.RobotFileParser()
    robots_url = urllib.parse.urljoin(base, "/robots.txt")
    robots.set_url(robots_url)

    if requests is None:
        robots.allow_all = True
        _ROBOTS_CACHE[base] = robots
        return robots

    try:
        response = requests.get(
            robots_url,
            headers={"User-Agent": USER_AGENT},
            timeout=3,
        )
    except requests.RequestException as exc:
        logger.info("robots.txt fetch failed for %s, defaulting to allow: %s", base, exc)
        robots.allow_all = True
        _ROBOTS_CACHE[base] = robots
        return robots

    if response.status_code == 200:
        robots.parse(response.text.splitlines())
    else:
        # Non-200 (often 403 from API edge servers). Don't enforce.
        logger.info("robots.txt at %s returned %s; defaulting to allow", robots_url, response.status_code)
        robots.allow_all = True
    _ROBOTS_CACHE[base] = robots
    return robots


def _respect_rate_limit(url: str) -> None:
    domain = urllib.parse.urlparse(url).netloc
    now = time.monotonic()
    last = _LAST_REQUEST_AT.get(domain)
    if last is not None:
        elapsed = now - last
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
    _LAST_REQUEST_AT[domain] = time.monotonic()


def request_json(url: str, *, timeout: int = 10) -> Any:
    return _request(url, timeout=timeout).json()


def request_text(url: str, *, timeout: int = 10) -> str:
    return _request(url, timeout=timeout).text


def _request(url: str, *, timeout: int) -> Any:
    if requests is None:
        raise SourceFetchError("requests dependency is not installed")

    robots = _robots_for(url)
    if not robots.can_fetch(USER_AGENT, url):
        raise SourceFetchError(f"robots.txt disallows {url}")

    _respect_rate_limit(url)
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
                "Referer": "https://www.wnba.com/",
                "x-nba-stats-origin": "stats",
                "x-nba-stats-token": "true",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        raise SourceFetchError(str(exc)) from exc
