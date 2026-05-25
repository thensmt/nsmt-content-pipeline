"""ESPN fetch and fixture loading for the Mystics postgame MVP."""

from __future__ import annotations

import json
from datetime import date, timezone
from pathlib import Path
from typing import Any

from ingestion.cache import ESPN_TTL_MIN, get_cached_json, iso_utc, request_json
from newsroom.common import PROJECT_ROOT, SPORT, LEAGUE_SLUG, TEAM_ID, TEAM_NAME, _parse_espn_datetime

SCHEDULE_URL_TMPL = (
    "https://site.api.espn.com/apis/site/v2/sports/"
    f"{SPORT}/{LEAGUE_SLUG}/teams/{TEAM_ID}/schedule?season={{season}}"
)
SCOREBOARD_URL_TMPL = (
    "https://site.api.espn.com/apis/site/v2/sports/"
    f"{SPORT}/{LEAGUE_SLUG}/scoreboard?dates={{date_key}}&limit=100"
)
SUMMARY_URL_TMPL = (
    "https://site.api.espn.com/apis/site/v2/sports/"
    f"{SPORT}/{LEAGUE_SLUG}/summary?event={{event_id}}"
)

def fetch_espn_payloads(*, as_of: date | None = None, season: int | None = None) -> dict[str, Any]:
    """Fetch schedule, scoreboard, and summary payloads for the latest final.

    ESPN's team schedule endpoint is useful for candidate dates, but it does
    not reliably carry final/in-progress status. We use daily scoreboard
    payloads to verify completion and then pull the summary endpoint for the
    selected event.
    """
    as_of = as_of or date.today()
    season = season or as_of.year

    schedule_url = SCHEDULE_URL_TMPL.format(season=season)
    schedule = get_cached_json(
        "espn",
        f"mystics_schedule_{season}",
        ESPN_TTL_MIN,
        lambda: request_json(schedule_url),
    )

    scoreboards: dict[str, Any] = {}
    selected_event: dict[str, Any] | None = None
    selected_date_key = ""

    for date_key in _candidate_scoreboard_dates(schedule, as_of):
        scoreboard_url = SCOREBOARD_URL_TMPL.format(date_key=date_key)
        scoreboard = get_cached_json(
            "espn",
            f"mystics_scoreboard_{date_key}",
            ESPN_TTL_MIN,
            lambda url=scoreboard_url: request_json(url),
        )
        scoreboards[date_key] = scoreboard
        selected_event = _latest_completed_mystics_event(scoreboard)
        if selected_event:
            selected_date_key = date_key
            break

    if not selected_event:
        raise RuntimeError(f"No completed Mystics game found on or before {as_of.isoformat()}")

    event_id = str(selected_event.get("id") or "")
    if not event_id:
        raise RuntimeError("Completed Mystics event did not include an ESPN event id")

    summary_url = SUMMARY_URL_TMPL.format(event_id=event_id)
    summary = get_cached_json(
        "espn",
        f"mystics_summary_{event_id}",
        ESPN_TTL_MIN,
        lambda: request_json(summary_url),
    )

    return {
        "retrieved_at": iso_utc(),
        "as_of": as_of.isoformat(),
        "season": season,
        "schedule_url": schedule_url,
        "scoreboard_url": SCOREBOARD_URL_TMPL.format(date_key=selected_date_key),
        "summary_url": summary_url,
        "schedule": schedule,
        "scoreboards": scoreboards,
        "event": selected_event,
        "summary": summary,
    }


def load_fixture_payload(path: Path | str) -> dict[str, Any]:
    fixture_path = Path(path)
    if not fixture_path.is_absolute():
        fixture_path = PROJECT_ROOT / fixture_path
    return json.loads(fixture_path.read_text())


def _candidate_scoreboard_dates(schedule: dict[str, Any], as_of: date) -> list[str]:
    dates: set[str] = set()
    for event in schedule.get("events") or []:
        event_dt = _parse_espn_datetime(event.get("date"))
        if not event_dt:
            continue
        event_date = event_dt.date()
        if event_date <= as_of:
            dates.add(event_date.strftime("%Y%m%d"))
            # ESPN scoreboard buckets some late games by local date. Checking
            # the previous UTC date catches 00:00Z games like WSH at DAL.
            dates.add((event_date.fromordinal(event_date.toordinal() - 1)).strftime("%Y%m%d"))
    return sorted(dates, reverse=True)


def _latest_completed_mystics_event(scoreboard: dict[str, Any]) -> dict[str, Any] | None:
    candidates = []
    for event in scoreboard.get("events") or []:
        if not _event_has_mystics(event):
            continue
        status = _status(event)
        if status.get("completed"):
            candidates.append(event)
    candidates.sort(key=lambda event: _event_date(event), reverse=True)
    return candidates[0] if candidates else None


def _event_from_fixture_scoreboards(payloads: dict[str, Any]) -> dict[str, Any] | None:
    for scoreboard in (payloads.get("scoreboards") or {}).values():
        event = _latest_completed_mystics_event(scoreboard)
        if event:
            return event
    return None


def _event_has_mystics(event: dict[str, Any]) -> bool:
    competitors = (event.get("competitions") or [{}])[0].get("competitors") or []
    return any(
        str((comp.get("team") or {}).get("id") or comp.get("id") or "") == TEAM_ID
        or (comp.get("team") or {}).get("displayName") == TEAM_NAME
        for comp in competitors
    )


def _status(event: dict[str, Any]) -> dict[str, Any]:
    status_type = ((event.get("status") or {}).get("type") or {})
    return {
        "name": status_type.get("name") or "",
        "description": status_type.get("description") or status_type.get("detail") or "",
        "completed": bool(status_type.get("completed")),
    }


def _event_date(event: dict[str, Any]) -> str:
    dt = _parse_espn_datetime(event.get("date"))
    if dt:
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return str(event.get("date") or "")
