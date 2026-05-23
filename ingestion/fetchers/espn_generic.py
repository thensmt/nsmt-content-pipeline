"""Sport-agnostic ESPN fetcher.

Parameterized by (sport, league_slug, team_id, team_name) so it works for any
team in any sport ESPN exposes via site.api.espn.com. Hits scoreboard + summary
endpoints, extracts per-player boxscores in the sport-neutral `BoxscoreEntry`
shape — `stats: dict[str, str]` carries whatever labels ESPN returns for that
section in that sport (batting / pitching / players / skaters / goaltenders /
etc.).

Why this exists alongside `espn.py`:
- `espn.py` is the original Mystics-only fetcher. Hardcoded WNBA / team_id 14.
  It still works for the Mystics path; keep using it there to avoid regression.
- `espn_generic.py` is the path forward for every other team / sport. Use it
  for the Nationals (MLB), Capitals (NHL), Spirit (NWSL), Defenders (UFL),
  Commanders (NFL), etc.

The two paths emit the same outer dict shape (`game_summary`, `top_performers`,
`recent_team_context`, `editorial_angle_candidates`, `source_links`,
`confidence_notes`, plus boxscore fields). The DIFFERENCE is that `espn.py`
emits a `boxscore.rows` (basketball-shaped) while `espn_generic.py` emits a
`boxscore.entries` (sport-neutral). The prompt renderer in `generate_content
._format_boxscore_rows` handles both.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Callable

from ingestion.cache import (
    ESPN_TTL_MIN,
    SourceFetchError,
    date_to_utc_iso,
    get_cached_json,
    request_json,
)


logger = logging.getLogger(__name__)

SCOREBOARD_URL_TMPL = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_slug}/scoreboard"
SUMMARY_URL_TMPL    = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_slug}/summary"


def fetch(
    *,
    sport: str,
    league_slug: str,
    team_id: str,
    team_name: str,
    target_date: date,
    retrieved_at: str,
) -> dict[str, Any]:
    """Pull the team's game for `target_date` from ESPN. Returns the same
    fetcher-style dict as `espn.py` but with `boxscore.entries` (sport-neutral)
    instead of `boxscore.rows` (basketball-only)."""
    date_key = target_date.strftime("%Y%m%d")
    scoreboard_url = (
        f"{SCOREBOARD_URL_TMPL.format(sport=sport, league_slug=league_slug)}"
        f"?dates={date_key}"
    )

    try:
        payload = get_cached_json(
            "espn",
            f"{league_slug}_scoreboard_{date_key}",
            ESPN_TTL_MIN,
            lambda: request_json(scoreboard_url),
        )
    except (SourceFetchError, ValueError) as exc:
        logger.warning("ESPN %s scoreboard fetch failed: %s", league_slug, exc)
        return _empty_result([f"ESPN {league_slug} scoreboard unavailable: {exc}"])

    events = payload.get("events", []) if isinstance(payload, dict) else []
    event = _find_team_game(events, team_id, team_name)
    sources = [_source(f"ESPN {league_slug} scoreboard", scoreboard_url, target_date, retrieved_at, 0.9)]

    if not event:
        return _empty_result([], sources=sources)

    game_id = str(event.get("id") or "")
    summary, summary_note = _fetch_summary(sport, league_slug, game_id) if game_id else (None, "no game_id on event")
    notes: list[str] = []
    if summary is None and summary_note:
        notes.append(summary_note)
    if summary is not None:
        summary_url = (
            f"{SUMMARY_URL_TMPL.format(sport=sport, league_slug=league_slug)}"
            f"?event={game_id}"
        )
        sources.append(_source(f"ESPN {league_slug} summary", summary_url, target_date, retrieved_at, 0.92))

    return {
        "game_summary": _extract_game_summary(event, summary, target_date, team_id, team_name),
        "top_performers": _extract_top_performers(summary, team_id, team_name, sport),
        "recent_team_context": _extract_context(event, summary, target_date, team_id, team_name),
        "editorial_angle_candidates": [],
        "boxscore": _extract_team_boxscore(summary, team_id, team_name, sport, league_slug),
        "opponent_boxscore": _extract_team_boxscore(summary, team_id, team_name, sport, league_slug, opponent=True),
        "source_links": sources,
        "confidence_notes": notes,
    }


# ── internal helpers ──────────────────────────────────────────────────────────

def _empty_result(notes: list[str], sources: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "game_summary": None,
        "top_performers": [],
        "recent_team_context": "",
        "editorial_angle_candidates": [],
        "boxscore": None,
        "opponent_boxscore": None,
        "source_links": sources or [],
        "confidence_notes": notes,
    }


def _source(source_name: str, url: str, target_date: date, retrieved_at: str, confidence: float) -> dict[str, Any]:
    return {
        "source_name": source_name,
        "source_url": url,
        "published_at": date_to_utc_iso(target_date.isoformat()),
        "retrieved_at": retrieved_at,
        "confidence": confidence,
    }


def _fetch_summary(sport: str, league_slug: str, game_id: str) -> tuple[dict[str, Any] | None, str]:
    url = f"{SUMMARY_URL_TMPL.format(sport=sport, league_slug=league_slug)}?event={game_id}"
    try:
        payload = get_cached_json(
            "espn",
            f"{league_slug}_summary_{game_id}",
            ESPN_TTL_MIN,
            lambda: request_json(url),
        )
    except (SourceFetchError, ValueError) as exc:
        logger.warning("ESPN %s summary fetch failed: %s", league_slug, exc)
        return None, f"ESPN {league_slug} summary unavailable: {exc}"
    if not isinstance(payload, dict):
        return None, f"ESPN {league_slug} summary returned non-dict payload"
    return payload, ""


def _find_team_game(events: list[dict[str, Any]], team_id: str, team_name: str) -> dict[str, Any] | None:
    """Locate the event containing our team. Match by ESPN id, uid suffix, or
    case-insensitive display/short name."""
    team_id_str = str(team_id)
    team_lower = team_name.lower()
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
            if team_id_str in identifiers or team_lower in identifiers:
                return event
    return None


def _competitor(event_competitors: list[dict[str, Any]], team_id: str, team_name: str) -> dict[str, Any]:
    """Return the competitor entry for our team, or the opponent if we want
    the other side (caller can iterate and pick whichever isn't ours)."""
    team_id_str = str(team_id)
    for c in event_competitors:
        t = c.get("team") or {}
        if str(t.get("id")) == team_id_str or t.get("displayName") == team_name:
            return c
    return {}


def _opponent(event_competitors: list[dict[str, Any]], team_id: str, team_name: str) -> dict[str, Any]:
    our_id = str(team_id)
    for c in event_competitors:
        t = c.get("team") or {}
        if str(t.get("id")) != our_id and t.get("displayName") != team_name:
            return c
    return {}


def _extract_game_summary(event: dict[str, Any], summary: dict[str, Any] | None,
                          target_date: date, team_id: str, team_name: str) -> dict[str, Any]:
    competition = event.get("competitions", [{}])[0]
    competitors = competition.get("competitors", [])
    ours = _competitor(competitors, team_id, team_name)
    opp = _opponent(competitors, team_id, team_name)

    our_score = ours.get("score", "?")
    opp_score = opp.get("score", "?")
    opp_name = opp.get("team", {}).get("displayName", "Opponent")
    home_away = ours.get("homeAway", "")
    if home_away == "home":
        score = f"{team_name} {our_score}, {opp_name} {opp_score}"
    else:
        score = f"{opp_name} {opp_score}, {team_name} {our_score}"

    out: dict[str, Any] = {
        "score": score,
        "venue": competition.get("venue", {}).get("fullName", ""),
        "opponent": opp_name,
        "date": _event_date(event, target_date),
        "status": event.get("status", {}).get("type", {}).get("description", ""),
        "home_away": home_away,
    }

    linescore = _linescore_string(summary, team_id, team_name)
    if linescore:
        out["linescore"] = linescore

    attendance = _attendance(summary)
    if attendance:
        out["attendance"] = attendance

    return out


def _event_date(event: dict[str, Any], target_date: date) -> str:
    event_date = str(event.get("date") or "")
    if event_date.endswith("Z"):
        return event_date
    return date_to_utc_iso(target_date.isoformat())


def _team_boxscore_block(summary: dict[str, Any] | None, team_id: str,
                         team_name: str, opponent: bool = False) -> dict[str, Any]:
    """Find the boxscore block for one team (or the opposing team when
    `opponent=True`). ESPN's summary always has exactly two teams.

    Matches by team_id OR team_name — both are tried because the TEAMS list
    `espn_id` values aren't always consistent with what ESPN's summary
    endpoint returns. The name match is the robust fallback."""
    if not summary:
        return {}
    blocks = (summary.get("boxscore") or {}).get("players") or []
    team_id_str = str(team_id)
    if opponent:
        for blk in blocks:
            t = blk.get("team") or {}
            if str(t.get("id")) != team_id_str and t.get("displayName") != team_name:
                return blk
        return {}
    for blk in blocks:
        t = blk.get("team") or {}
        if str(t.get("id")) == team_id_str or t.get("displayName") == team_name:
            return blk
    return {}


def _extract_team_boxscore(summary: dict[str, Any] | None, team_id: str,
                           team_name: str, sport: str, league: str,
                           opponent: bool = False) -> dict[str, Any] | None:
    """Return a structured TeamBoxscore dict with sport-neutral entries, or
    None when ESPN didn't return stats (preseason / not-started / DNP-only)."""
    block = _team_boxscore_block(summary, team_id, team_name, opponent=opponent)
    if not block:
        return None

    team = block.get("team") or {}
    competitors = ((summary or {}).get("header") or {}).get("competitions", [{}])[0].get("competitors", [])
    home_away = ""
    for c in competitors:
        ct = c.get("team") or {}
        if str(ct.get("id")) == str(team.get("id")):
            home_away = c.get("homeAway", "")
            break

    statistics_blocks = block.get("statistics") or []
    if not statistics_blocks:
        return None

    entries: list[dict[str, Any]] = []
    for stats_block in statistics_blocks:
        section = (stats_block.get("type") or stats_block.get("name") or "players").lower()
        labels = stats_block.get("labels") or []
        athletes = stats_block.get("athletes") or []
        if not labels or not athletes:
            continue
        for athlete_entry in athletes:
            row_stats = athlete_entry.get("stats") or []
            if not row_stats:
                continue
            athlete = athlete_entry.get("athlete") or {}
            name = athlete.get("displayName") or ""
            if not name:
                continue
            position = (athlete.get("position") or {}).get("abbreviation", "")
            stats: dict[str, str] = {}
            for i, label in enumerate(labels):
                if i < len(row_stats):
                    value = row_stats[i]
                    if value not in (None, ""):
                        stats[label] = str(value)
            entries.append({
                "player": name,
                "position": position,
                "starter": bool(athlete_entry.get("starter")),
                "section": section,
                "stats": stats,
            })

    if not entries:
        return None

    return {
        "team_name": team.get("displayName") or "",
        "team_abbr": team.get("abbreviation") or "",
        "home_away": home_away,
        "sport": sport,
        "league": league,
        "entries": entries,
    }


def _extract_top_performers(summary: dict[str, Any] | None, team_id: str,
                            team_name: str, sport: str) -> list[dict[str, str]]:
    """Generic "top performers" from boxscore data — sport-aware ranking key
    when possible, otherwise just take first 3-5 entries from the primary
    stats section."""
    if not summary:
        return []
    block = _team_boxscore_block(summary, team_id, team_name, opponent=False)
    if not block:
        return []
    stats_blocks = block.get("statistics") or []
    if not stats_blocks:
        return []

    # Use the FIRST statistics section as the ranking source (batting for
    # baseball, players for basketball, skaters for hockey, etc.). For sports
    # with batting + pitching split, batting is usually first and is the
    # "headline" stat set for fans.
    primary = stats_blocks[0]
    labels = primary.get("labels") or []
    athletes = primary.get("athletes") or []
    if not labels or not athletes:
        return []

    # Sport-specific ranking key for the headliners. For unknown sports,
    # we just take the first few in ESPN's order (which is typically the
    # batting order or starting lineup).
    rank_key = _sport_rank_key(sport, labels)

    def get_val(entry: dict[str, Any], label: str) -> str:
        stats = entry.get("stats") or []
        if label not in labels:
            return ""
        idx = labels.index(label)
        if idx >= len(stats):
            return ""
        return str(stats[idx] or "")

    scored = []
    for entry in athletes:
        if not entry.get("stats"):
            continue
        name = (entry.get("athlete") or {}).get("displayName") or ""
        if not name:
            continue
        score = 0.0
        for label, weight in rank_key.items():
            try:
                score += weight * float(get_val(entry, label) or 0)
            except ValueError:
                pass
        # Build a compact stat line — show 3-4 most relevant stats for the sport
        line_labels = _sport_top_line_labels(sport, labels)
        line_chunks = []
        for label in line_labels:
            val = get_val(entry, label)
            if val:
                line_chunks.append(f"{val} {label}")
        scored.append({
            "player": name,
            "stat_line": ", ".join(line_chunks) if line_chunks else "",
            "note": f"ESPN boxscore ({primary.get('type') or 'primary'})",
            "_score": score,
        })

    scored.sort(key=lambda r: r["_score"], reverse=True)
    return [{k: v for k, v in r.items() if k != "_score"} for r in scored[:5]]


def _sport_rank_key(sport: str, labels: list[str]) -> dict[str, float]:
    """Per-sport weight map for ranking 'top performers'. Each key is a label
    that may appear in the boxscore; weights pick the headliner intuitively.
    Returns empty dict for unknown sports (resulting in order = ESPN's order)."""
    sport_l = (sport or "").lower()
    if sport_l == "basketball":
        return {"PTS": 1.0, "REB": 0.5, "AST": 1.0}
    if sport_l == "baseball":
        # Batting: weight runs created loosely
        return {"R": 1.0, "H": 1.0, "RBI": 1.5, "HR": 2.0}
    if sport_l == "hockey":
        return {"G": 2.0, "A": 1.0, "+/-": 0.3}
    if sport_l == "football":
        return {"TD": 6.0, "YDS": 0.05, "REC": 0.5}
    if sport_l == "soccer":
        return {"G": 2.0, "A": 1.0, "SH": 0.2}
    return {}


def _sport_top_line_labels(sport: str, labels: list[str]) -> list[str]:
    """The 3-4 stat labels we surface in a top-performer's one-line summary.
    Falls back to the first 4 labels when sport is unknown."""
    sport_l = (sport or "").lower()
    if sport_l == "basketball":
        return [l for l in ["PTS", "REB", "AST", "FG"] if l in labels]
    if sport_l == "baseball":
        return [l for l in ["H-AB", "R", "RBI", "HR", "BB"] if l in labels]
    if sport_l == "hockey":
        return [l for l in ["G", "A", "+/-", "SOG"] if l in labels]
    if sport_l == "football":
        return [l for l in ["YDS", "TD", "CMP", "REC", "CAR"] if l in labels]
    if sport_l == "soccer":
        return [l for l in ["G", "A", "SH", "ST"] if l in labels]
    return labels[:4]


def _linescore_string(summary: dict[str, Any] | None, team_id: str, team_name: str) -> str:
    """Compact per-period scoring string, e.g. for basketball:
    'WSH: 22-18-21-21 | OPP: 19-19-18-19'. For baseball, inning-by-inning."""
    if not summary:
        return ""
    competitors = (summary.get("header") or {}).get("competitions", [{}])[0].get("competitors", [])
    if len(competitors) != 2:
        return ""
    parts = []
    for c in competitors:
        abbr = (c.get("team") or {}).get("abbreviation", "")
        scores = [str(ls.get("displayValue", "")) for ls in (c.get("linescores") or [])]
        if abbr and scores:
            parts.append(f"{abbr}: {'-'.join(scores)}")
    return " | ".join(parts)


def _attendance(summary: dict[str, Any] | None) -> int:
    if not summary:
        return 0
    val = (summary.get("gameInfo") or {}).get("attendance")
    if isinstance(val, int) and val > 0:
        return val
    return 0


def _extract_context(event: dict[str, Any], summary: dict[str, Any] | None,
                     target_date: date, team_id: str, team_name: str) -> str:
    """1-3 sentence narrative context: status, headline, linescore."""
    sentences: list[str] = []
    status = event.get("status", {}).get("type", {}).get("description", "")
    if status:
        sentences.append(f"ESPN listed the {team_name} game as {status}.")
    notes = ((event.get("competitions") or [{}])[0].get("notes") or [])
    if notes:
        headline = notes[0].get("headline") or notes[0].get("type")
        if headline:
            sentences.append(str(headline))
    if summary:
        linescore = _linescore_string(summary, team_id, team_name)
        if linescore:
            sentences.append(f"Period scores — {linescore}.")
    return " ".join(sentences).strip()
