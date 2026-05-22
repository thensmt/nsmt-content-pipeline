"""ESPN WNBA scoreboard fetcher for Washington Mystics packets."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from ingestion.cache import ESPN_TTL_MIN, SourceFetchError, date_to_utc_iso, get_cached_json, request_json


logger = logging.getLogger(__name__)

TEAM_NAME = "Washington Mystics"
ESPN_TEAM_ID = "14"
SPORT = "basketball"
LEAGUE_SLUG = "wnba"


def fetch(target_date: date, retrieved_at: str) -> dict[str, Any]:
    date_key = target_date.strftime("%Y%m%d")
    url = (
        "https://site.api.espn.com/apis/site/v2/sports/"
        f"{SPORT}/{LEAGUE_SLUG}/scoreboard?dates={date_key}"
    )

    try:
        payload = get_cached_json(
            "espn",
            f"wnba_scoreboard_{date_key}",
            ESPN_TTL_MIN,
            lambda: request_json(url),
        )
    except (SourceFetchError, ValueError) as exc:
        logger.warning("ESPN fetch failed: %s", exc)
        return {
            "game_summary": None,
            "top_performers": [],
            "recent_team_context": "",
            "source_links": [],
            "confidence_notes": [f"ESPN WNBA scoreboard unavailable: {exc}"],
        }

    events = payload.get("events", []) if isinstance(payload, dict) else []
    event = _find_team_game(events)
    source_link = {
        "source_name": "ESPN WNBA scoreboard",
        "source_url": url,
        "published_at": date_to_utc_iso(target_date.isoformat()),
        "retrieved_at": retrieved_at,
        "confidence": 0.9,
    }

    if not event:
        return {
            "game_summary": None,
            "top_performers": [],
            "recent_team_context": "",
            "source_links": [source_link],
            "confidence_notes": [],
        }

    return {
        "game_summary": _extract_game_summary(event, target_date),
        "top_performers": _extract_top_performers(event),
        "recent_team_context": _extract_context(event),
        "source_links": [source_link],
        "confidence_notes": [],
    }


def _find_team_game(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    team_lower = TEAM_NAME.lower()
    for event in events:
        competitors = event.get("competitions", [{}])[0].get("competitors", [])
        for competitor in competitors:
            team = competitor.get("team", {})
            identifiers = {
                str(team.get("id", "")),
                str(team.get("uid", "")).split(":")[-1],
                str(team.get("displayName", "")).lower(),
                str(team.get("name", "")).lower(),
            }
            if ESPN_TEAM_ID in identifiers or team_lower in identifiers:
                return event
    return None


def _extract_game_summary(event: dict[str, Any], target_date: date) -> dict[str, str]:
    competition = event.get("competitions", [{}])[0]
    competitors = competition.get("competitors", [])
    mystics = _team_competitor(competitors)
    opponent = next((item for item in competitors if item is not mystics), {})

    mystics_score = mystics.get("score", "?")
    opponent_score = opponent.get("score", "?")
    opponent_name = opponent.get("team", {}).get("displayName", "Opponent")
    home_away = mystics.get("homeAway", "")
    score = f"{TEAM_NAME} {mystics_score}, {opponent_name} {opponent_score}"
    if home_away == "away":
        score = f"{opponent_name} {opponent_score}, {TEAM_NAME} {mystics_score}"

    return {
        "score": score,
        "venue": competition.get("venue", {}).get("fullName", ""),
        "opponent": opponent_name,
        "date": _event_date(event, target_date),
        "status": event.get("status", {}).get("type", {}).get("description", ""),
        "home_away": home_away,
    }


def _team_competitor(competitors: list[dict[str, Any]]) -> dict[str, Any]:
    for competitor in competitors:
        team = competitor.get("team", {})
        if str(team.get("id")) == ESPN_TEAM_ID or team.get("displayName") == TEAM_NAME:
            return competitor
    return {}


def _event_date(event: dict[str, Any], target_date: date) -> str:
    event_date = str(event.get("date") or "")
    if event_date.endswith("Z"):
        return event_date
    return date_to_utc_iso(target_date.isoformat())


def _extract_top_performers(event: dict[str, Any]) -> list[dict[str, str]]:
    performers: list[dict[str, str]] = []
    competitors = event.get("competitions", [{}])[0].get("competitors", [])
    for competitor in competitors:
        team_name = competitor.get("team", {}).get("displayName", "")
        for leader_category in competitor.get("leaders", []) or []:
            stat_name = leader_category.get("shortDisplayName") or leader_category.get("displayName") or "stat"
            for leader in leader_category.get("leaders", []) or []:
                athlete = leader.get("athlete", {}).get("displayName")
                value = leader.get("displayValue") or str(leader.get("value", ""))
                if athlete and value:
                    performers.append(
                        {
                            "player": athlete,
                            "stat_line": f"{stat_name}: {value}",
                            "note": f"ESPN listed leader for {team_name}".strip(),
                        }
                    )
    return performers[:6]


def _extract_context(event: dict[str, Any]) -> str:
    status = event.get("status", {}).get("type", {}).get("description")
    summary = _safe_summary(event)
    if summary and status:
        return f"ESPN listed the Mystics game as {status}. {summary}"
    if status:
        return f"ESPN listed the Mystics game as {status}."
    return summary


def _safe_summary(event: dict[str, Any]) -> str:
    headline = ((event.get("competitions") or [{}])[0].get("notes") or [])
    if headline:
        text = headline[0].get("headline") or headline[0].get("type")
        if text:
            return str(text)
    return ""

