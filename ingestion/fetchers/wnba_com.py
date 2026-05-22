"""WNBA.com Stats and league page fetcher."""

from __future__ import annotations

import html
import logging
import re
from datetime import date
from typing import Any

from ingestion.cache import WNBA_NEWS_TTL_MIN, SourceFetchError, date_to_utc_iso, get_cached_json, request_json, request_text


logger = logging.getLogger(__name__)

MYSTICS_TEAM_ID = 1611661322
MYSTICS_ABBR = "WAS"
SCOREBOARD_URL = "https://stats.wnba.com/stats/scoreboardv2"
BOXSCORE_URL = "https://stats.wnba.com/stats/boxscoretraditionalv2"
STANDINGS_URL = "https://www.wnba.com/standings"
INJURY_REPORT_URL = "https://www.wnba.com/wnba-injury-report"


def fetch(target_date: date, retrieved_at: str) -> dict[str, Any]:
    notes: list[str] = []
    sources: list[dict[str, Any]] = []
    top_performers: list[dict[str, str]] = []
    game_summary: dict[str, str] | None = None
    standings_context = ""
    injuries: list[dict[str, str]] = []

    scoreboard_url = _scoreboard_url(target_date)
    try:
        scoreboard = get_cached_json(
            "wnba_com",
            f"scoreboardv2_{target_date.isoformat()}",
            WNBA_NEWS_TTL_MIN,
            lambda: request_json(scoreboard_url),
        )
        sources.append(_source("WNBA.com Stats scoreboard", scoreboard_url, target_date, retrieved_at, 0.85))
        game_summary = _game_summary_from_scoreboard(scoreboard, target_date)
        standings_context = _standings_from_scoreboard(scoreboard)
        game_id = _game_id_from_scoreboard(scoreboard)
        if game_id:
            box = _fetch_box_score(game_id)
            if box:
                top_performers = _top_performers_from_box(box)
                sources.append(_source("WNBA.com box score", _boxscore_url(game_id), target_date, retrieved_at, 0.82))
    except (SourceFetchError, ValueError) as exc:
        logger.warning("WNBA.com Stats fetch failed: %s", exc)
        notes.append(f"WNBA.com Stats scoreboard unavailable: {exc}")

    if not standings_context:
        fallback_context, fallback_note = _fetch_standings_page(target_date, retrieved_at, sources)
        standings_context = fallback_context
        if fallback_note:
            notes.append(fallback_note)

    injury_rows, injury_note = _fetch_injury_report(target_date, retrieved_at, sources)
    injuries.extend(injury_rows)
    if injury_note:
        notes.append(injury_note)

    return {
        "game_summary": game_summary,
        "top_performers": top_performers,
        "standings_context": standings_context,
        "injuries_or_availability": injuries,
        "source_links": sources,
        "confidence_notes": notes,
    }


def _scoreboard_url(target_date: date) -> str:
    game_date = target_date.strftime("%m/%d/%Y")
    return f"{SCOREBOARD_URL}?DayOffset=0&GameDate={game_date}&LeagueID=10"


def _boxscore_url(game_id: str) -> str:
    return (
        f"{BOXSCORE_URL}?GameID={game_id}&StartPeriod=0&EndPeriod=0"
        "&StartRange=0&EndRange=0&RangeType=0"
    )


def _source(source_name: str, url: str, target_date: date, retrieved_at: str, confidence: float) -> dict[str, Any]:
    return {
        "source_name": source_name,
        "source_url": url,
        "published_at": date_to_utc_iso(target_date.isoformat()),
        "retrieved_at": retrieved_at,
        "confidence": confidence,
    }


def _result_set(payload: dict[str, Any], name: str) -> list[dict[str, Any]]:
    for result_set in payload.get("resultSets", []) or []:
        if result_set.get("name") != name:
            continue
        headers = result_set.get("headers", [])
        return [dict(zip(headers, row)) for row in result_set.get("rowSet", [])]
    return []


def _game_id_from_scoreboard(payload: dict[str, Any]) -> str | None:
    for row in _result_set(payload, "GameHeader"):
        if MYSTICS_TEAM_ID in (row.get("HOME_TEAM_ID"), row.get("VISITOR_TEAM_ID")):
            return str(row.get("GAME_ID") or "")
    return None


def _game_summary_from_scoreboard(payload: dict[str, Any], target_date: date) -> dict[str, str] | None:
    game_rows = _result_set(payload, "GameHeader")
    line_rows = _result_set(payload, "LineScore")
    for game in game_rows:
        if MYSTICS_TEAM_ID not in (game.get("HOME_TEAM_ID"), game.get("VISITOR_TEAM_ID")):
            continue
        home_id = game.get("HOME_TEAM_ID")
        visitor_id = game.get("VISITOR_TEAM_ID")
        home_name = _team_name(game, "HOME")
        visitor_name = _team_name(game, "VISITOR")
        home_score = _score_for(line_rows, home_id)
        visitor_score = _score_for(line_rows, visitor_id)
        if home_id == MYSTICS_TEAM_ID:
            opponent = visitor_name
            home_away = "home"
        else:
            opponent = home_name
            home_away = "away"
        return {
            "score": f"{visitor_name} {visitor_score}, {home_name} {home_score}",
            "venue": str(game.get("ARENA_NAME") or ""),
            "opponent": opponent,
            "date": _game_date(game, target_date),
            "status": str(game.get("GAME_STATUS_TEXT") or ""),
            "home_away": home_away,
        }
    return None


def _team_name(row: dict[str, Any], prefix: str) -> str:
    city = row.get(f"{prefix}_TEAM_CITY") or ""
    name = row.get(f"{prefix}_TEAM_NAME") or ""
    combined = f"{city} {name}".strip()
    return combined or str(row.get(f"{prefix}_TEAM_ABBREVIATION") or "Opponent")


def _score_for(line_rows: list[dict[str, Any]], team_id: Any) -> str:
    for row in line_rows:
        if row.get("TEAM_ID") == team_id:
            return str(row.get("PTS") if row.get("PTS") is not None else "?")
    return "?"


def _game_date(game: dict[str, Any], target_date: date) -> str:
    value = str(game.get("GAME_DATE_EST") or "").strip()
    if re.match(r"\d{4}-\d{2}-\d{2}T", value):
        return value if value.endswith("Z") else value + "Z"
    if re.match(r"\d{4}-\d{2}-\d{2}", value):
        return date_to_utc_iso(value[:10])
    return date_to_utc_iso(target_date.isoformat())


def _standings_from_scoreboard(payload: dict[str, Any]) -> str:
    rows = _result_set(payload, "EastConfStandingsByDay") + _result_set(payload, "WestConfStandingsByDay")
    for row in rows:
        if row.get("TEAM_ID") != MYSTICS_TEAM_ID:
            continue
        wins = row.get("W") or row.get("WINS")
        losses = row.get("L") or row.get("LOSSES")
        pct = row.get("W_PCT") or row.get("WIN_PCT")
        rank = row.get("CONF_RANK") or row.get("PLAYOFF_RANK") or row.get("TEAM_STANDINGS_SEQ")
        return f"WNBA.com lists Washington at {wins}-{losses}" + (
            f" ({pct})" if pct not in (None, "") else ""
        ) + (f", rank {rank} in its standings table." if rank not in (None, "") else ".")
    return ""


def _fetch_box_score(game_id: str) -> dict[str, Any] | None:
    try:
        return get_cached_json(
            "wnba_com",
            f"boxscoretraditionalv2_{game_id}",
            WNBA_NEWS_TTL_MIN,
            lambda: request_json(_boxscore_url(game_id)),
        )
    except (SourceFetchError, ValueError) as exc:
        logger.warning("WNBA.com box score fetch failed: %s", exc)
        return None


def _top_performers_from_box(payload: dict[str, Any]) -> list[dict[str, str]]:
    rows = _result_set(payload, "PlayerStats")
    mystics = [row for row in rows if row.get("TEAM_ID") == MYSTICS_TEAM_ID]
    mystics.sort(
        key=lambda row: (
            int(row.get("PTS") or 0),
            int(row.get("REB") or 0),
            int(row.get("AST") or 0),
        ),
        reverse=True,
    )
    performers = []
    for row in mystics[:4]:
        name = row.get("PLAYER_NAME")
        if not name:
            continue
        performers.append(
            {
                "player": str(name),
                "stat_line": f"{row.get('PTS', 0)} pts, {row.get('REB', 0)} reb, {row.get('AST', 0)} ast",
                "note": "WNBA.com box score Mystics leader",
            }
        )
    return performers


def _fetch_standings_page(
    target_date: date,
    retrieved_at: str,
    sources: list[dict[str, Any]],
) -> tuple[str, str]:
    try:
        html_text = get_cached_json(
            "wnba_com",
            f"standings_page_{target_date.isoformat()}",
            WNBA_NEWS_TTL_MIN,
            lambda: {"html": request_text(STANDINGS_URL)},
        ).get("html", "")
    except (AttributeError, SourceFetchError, ValueError) as exc:
        logger.warning("WNBA standings page fetch failed: %s", exc)
        return "", f"WNBA.com standings page unavailable: {exc}"

    text = _visible_text(html_text)
    match = re.search(
        r"(?P<rank>\d+)\s+WAS\s+(?P<w>\d+)\s+(?P<l>\d+)\s+(?P<pct>\d?\.\d{3})\s+(?P<gb>--|[\d.]+)",
        text,
    )
    sources.append(_source("WNBA.com standings", STANDINGS_URL, target_date, retrieved_at, 0.75))
    if not match:
        return "", "WNBA.com standings page fetched but Mystics row was not parsed"
    return (
        "WNBA.com standings list Washington "
        f"{match.group('w')}-{match.group('l')} ({match.group('pct')}), "
        f"rank {match.group('rank')} overall and {match.group('gb')} games back.",
        "",
    )


def _fetch_injury_report(
    target_date: date,
    retrieved_at: str,
    sources: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], str]:
    try:
        html_text = get_cached_json(
            "wnba_com",
            f"injury_report_{target_date.isoformat()}",
            WNBA_NEWS_TTL_MIN,
            lambda: {"html": request_text(INJURY_REPORT_URL)},
        ).get("html", "")
    except (AttributeError, SourceFetchError, ValueError) as exc:
        logger.warning("WNBA injury report fetch failed: %s", exc)
        return [], f"WNBA injury report unavailable: {exc}"

    text = _visible_text(html_text)
    rows = _parse_mystics_injuries(text)
    sources.append(_source("WNBA injury report", INJURY_REPORT_URL, target_date, retrieved_at, 0.78))
    if not rows:
        return [], "WNBA injury report returned no parsed Mystics availability rows; do not infer full availability"
    return rows, ""


def _parse_mystics_injuries(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for match in re.finditer(
        r"(Washington Mystics|WAS)\s+(?P<player>[A-Z][A-Za-z .'-]+?)\s+(?P<status>Out|Doubtful|Questionable|Probable|Available)\s+(?P<note>[^|]{0,160})",
        text,
    ):
        rows.append(
            {
                "player": match.group("player").strip(),
                "status": match.group("status"),
                "note": match.group("note").strip(),
                "source_url": INJURY_REPORT_URL,
            }
        )
    return rows[:6]


def _visible_text(html_text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html_text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text)

