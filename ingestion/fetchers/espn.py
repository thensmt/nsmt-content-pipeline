"""ESPN WNBA fetcher: scoreboard + summary endpoints for Mystics packets."""

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

SCOREBOARD_URL = f"https://site.api.espn.com/apis/site/v2/sports/{SPORT}/{LEAGUE_SLUG}/scoreboard"
SUMMARY_URL = f"https://site.api.espn.com/apis/site/v2/sports/{SPORT}/{LEAGUE_SLUG}/summary"


def fetch(target_date: date, retrieved_at: str) -> dict[str, Any]:
    date_key = target_date.strftime("%Y%m%d")
    scoreboard_url = f"{SCOREBOARD_URL}?dates={date_key}"

    try:
        payload = get_cached_json(
            "espn",
            f"wnba_scoreboard_{date_key}",
            ESPN_TTL_MIN,
            lambda: request_json(scoreboard_url),
        )
    except (SourceFetchError, ValueError) as exc:
        logger.warning("ESPN scoreboard fetch failed: %s", exc)
        return {
            "game_summary": None,
            "top_performers": [],
            "recent_team_context": "",
            "editorial_angle_candidates": [],
            "source_links": [],
            "confidence_notes": [f"ESPN WNBA scoreboard unavailable: {exc}"],
        }

    events = payload.get("events", []) if isinstance(payload, dict) else []
    event = _find_team_game(events)
    sources = [_source("ESPN WNBA scoreboard", scoreboard_url, target_date, retrieved_at, 0.9)]

    if not event:
        return {
            "game_summary": None,
            "top_performers": [],
            "recent_team_context": "",
            "editorial_angle_candidates": [],
            "source_links": sources,
            "confidence_notes": [],
        }

    game_id = str(event.get("id") or "")
    summary, summary_note = _fetch_summary(game_id) if game_id else (None, "ESPN summary skipped: no game_id")
    notes: list[str] = []
    if summary is None and summary_note:
        notes.append(summary_note)
    if summary is not None:
        sources.append(_source("ESPN WNBA summary", f"{SUMMARY_URL}?event={game_id}", target_date, retrieved_at, 0.92))

    return {
        "game_summary": _extract_game_summary(event, summary, target_date),
        "top_performers": _extract_top_performers(event, summary),
        "recent_team_context": _extract_context(event, summary, target_date),
        "editorial_angle_candidates": _narrative_angles(event, summary),
        "boxscore": _extract_team_boxscore(event, summary, mystics=True),
        "opponent_boxscore": _extract_team_boxscore(event, summary, mystics=False),
        "source_links": sources,
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


def _fetch_summary(game_id: str) -> tuple[dict[str, Any] | None, str]:
    url = f"{SUMMARY_URL}?event={game_id}"
    try:
        payload = get_cached_json(
            "espn",
            f"wnba_summary_{game_id}",
            ESPN_TTL_MIN,
            lambda: request_json(url),
        )
    except (SourceFetchError, ValueError) as exc:
        logger.warning("ESPN summary fetch failed: %s", exc)
        return None, f"ESPN WNBA summary unavailable: {exc}"
    if not isinstance(payload, dict):
        return None, "ESPN WNBA summary returned non-dict payload"
    return payload, ""


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


def _team_competitor(competitors: list[dict[str, Any]]) -> dict[str, Any]:
    for competitor in competitors:
        team = competitor.get("team", {})
        if str(team.get("id")) == ESPN_TEAM_ID or team.get("displayName") == TEAM_NAME:
            return competitor
    return {}


def _extract_game_summary(event: dict[str, Any], summary: dict[str, Any] | None, target_date: date) -> dict[str, Any]:
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

    out: dict[str, Any] = {
        "score": score,
        "venue": competition.get("venue", {}).get("fullName", ""),
        "opponent": opponent_name,
        "date": _event_date(event, target_date),
        "status": event.get("status", {}).get("type", {}).get("description", ""),
        "home_away": home_away,
    }

    linescore_line = _linescore_line(summary)
    if linescore_line:
        out["linescore"] = linescore_line

    attendance = _attendance(summary)
    if attendance:
        out["attendance"] = attendance

    return out


def _event_date(event: dict[str, Any], target_date: date) -> str:
    event_date = str(event.get("date") or "")
    if event_date.endswith("Z"):
        return event_date
    return date_to_utc_iso(target_date.isoformat())


def _extract_top_performers(event: dict[str, Any], summary: dict[str, Any] | None) -> list[dict[str, str]]:
    """Prefer real boxscore stats from the summary endpoint; fall back to scoreboard leaders."""
    boxscore_performers = _top_performers_from_boxscore(summary) if summary else []
    if boxscore_performers:
        return boxscore_performers

    # Fallback: scoreboard `leaders` (top 3-4 by stat category) — still Mystics-only
    competitors = event.get("competitions", [{}])[0].get("competitors", [])
    mystics = _team_competitor(competitors)
    if not mystics:
        return []
    team_name = mystics.get("team", {}).get("displayName", "") or TEAM_NAME
    performers: list[dict[str, str]] = []
    for leader_category in mystics.get("leaders", []) or []:
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


def _top_performers_from_boxscore(summary: dict[str, Any]) -> list[dict[str, str]]:
    """Return top Mystics performers sorted by composite (PTS + 0.5*REB + AST), filtering DNPs."""
    block = _mystics_boxscore_block(summary)
    if not block:
        return []
    stats_block = (block.get("statistics") or [{}])[0]
    labels = stats_block.get("labels") or []
    athletes = stats_block.get("athletes") or []
    if not labels or not athletes:
        return []

    idx = {label: labels.index(label) for label in labels}

    def _stat(stats: list[Any], label: str) -> str:
        i = idx.get(label)
        if i is None or i >= len(stats):
            return ""
        return str(stats[i] or "")

    def _int(value: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    scored = []
    for entry in athletes:
        if not entry.get("active", True) and not entry.get("stats"):
            continue
        stats = entry.get("stats") or []
        if not stats:
            continue
        name = (entry.get("athlete") or {}).get("displayName") or ""
        if not name:
            continue
        pts = _int(_stat(stats, "PTS"))
        reb = _int(_stat(stats, "REB"))
        ast = _int(_stat(stats, "AST"))
        composite = pts + 0.5 * reb + ast
        fg = _stat(stats, "FG")
        stat_line_parts = [f"{pts} PTS", f"{reb} REB", f"{ast} AST"]
        if fg and fg != "0-0":
            stat_line_parts.append(f"{fg} FG")
        scored.append(
            {
                "player": name,
                "stat_line": ", ".join(stat_line_parts),
                "note": "ESPN boxscore (Mystics)",
                "_composite": composite,
            }
        )

    scored.sort(key=lambda r: r["_composite"], reverse=True)
    return [{k: v for k, v in r.items() if k != "_composite"} for r in scored[:5]]


def _mystics_boxscore_block(summary: dict[str, Any]) -> dict[str, Any]:
    for block in (summary.get("boxscore") or {}).get("players") or []:
        team = block.get("team") or {}
        if str(team.get("id")) == ESPN_TEAM_ID or team.get("displayName") == TEAM_NAME:
            return block
    return {}


def _opponent_boxscore_block(summary: dict[str, Any]) -> dict[str, Any]:
    """Return the non-Mystics team's boxscore block. ESPN summary always has
    exactly two teams; we pick the one that isn't us."""
    for block in (summary.get("boxscore") or {}).get("players") or []:
        team = block.get("team") or {}
        if str(team.get("id")) != ESPN_TEAM_ID and team.get("displayName") != TEAM_NAME:
            return block
    return {}


def _extract_team_boxscore(event: dict[str, Any], summary: dict[str, Any] | None, mystics: bool) -> dict[str, Any] | None:
    """Return a structured TeamBoxscore dict for one side of the game, or None
    when ESPN didn't return stats yet (preseason / not-started / DNP-only).

    Designed to be the canonical per-game stat source for the writer prompt —
    the writer must reference these numbers rather than invent stat lines.
    """
    if not summary:
        return None
    block = _mystics_boxscore_block(summary) if mystics else _opponent_boxscore_block(summary)
    if not block:
        return None

    team = block.get("team") or {}
    competitors = event.get("competitions", [{}])[0].get("competitors", [])
    home_away = ""
    for c in competitors:
        ct = c.get("team") or {}
        if str(ct.get("id")) == str(team.get("id")):
            home_away = c.get("homeAway", "")
            break

    stats_block = (block.get("statistics") or [{}])[0]
    labels = stats_block.get("labels") or []
    athletes = stats_block.get("athletes") or []
    if not labels or not athletes:
        return None

    label_idx = {label: labels.index(label) for label in labels}

    def stat(stats: list[Any], label: str) -> str:
        i = label_idx.get(label)
        if i is None or i >= len(stats):
            return ""
        return str(stats[i] or "")

    def to_int(value: str) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    rows: list[dict[str, Any]] = []
    for entry in athletes:
        stats = entry.get("stats") or []
        if not stats:
            continue
        athlete = entry.get("athlete") or {}
        name = athlete.get("displayName") or ""
        if not name:
            continue
        position = (athlete.get("position") or {}).get("abbreviation", "")
        row: dict[str, Any] = {
            "player": name,
            "position": position,
            "starter": bool(entry.get("starter")),
        }
        minutes = stat(stats, "MIN")
        if minutes:
            row["minutes"] = minutes
        pts = to_int(stat(stats, "PTS"))
        if pts is not None:
            row["points"] = pts
        reb = to_int(stat(stats, "REB"))
        if reb is not None:
            row["rebounds"] = reb
        ast = to_int(stat(stats, "AST"))
        if ast is not None:
            row["assists"] = ast
        stl = to_int(stat(stats, "STL"))
        if stl is not None:
            row["steals"] = stl
        blk = to_int(stat(stats, "BLK"))
        if blk is not None:
            row["blocks"] = blk
        to = to_int(stat(stats, "TO"))
        if to is not None:
            row["turnovers"] = to
        fg = stat(stats, "FG")
        if fg:
            row["fg"] = fg
        three_pt = stat(stats, "3PT")
        if three_pt:
            row["three_pt"] = three_pt
        ft = stat(stats, "FT")
        if ft:
            row["ft"] = ft
        plus_minus = to_int(stat(stats, "+/-"))
        if plus_minus is not None:
            row["plus_minus"] = plus_minus
        rows.append(row)

    if not rows:
        return None

    return {
        "team_name": team.get("displayName") or "",
        "team_abbr": team.get("abbreviation") or "",
        "home_away": home_away,
        "rows": rows,
    }


def _linescore_line(summary: dict[str, Any] | None) -> str:
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


def _extract_context(event: dict[str, Any], summary: dict[str, Any] | None, target_date: date) -> str:
    """Stitch a 2-4 sentence narrative context from event status + summary plays + win prob."""
    competitors = event.get("competitions", [{}])[0].get("competitors", [])
    mystics = _team_competitor(competitors)
    opponent = next((item for item in competitors if item is not mystics), {})
    opponent_name = opponent.get("team", {}).get("displayName", "the opponent")
    status = event.get("status", {}).get("type", {}).get("description", "")

    sentences: list[str] = []
    if status:
        sentences.append(f"ESPN listed the Mystics game as {status}.")

    headline = _safe_summary(event)
    if headline:
        sentences.append(headline)

    if summary:
        linescore = _linescore_line(summary)
        if linescore:
            sentences.append(f"Quarter scores — {linescore}.")

        run = _biggest_run(summary)
        if run:
            sentences.append(run)

        swing = _win_prob_arc(summary)
        if swing:
            sentences.append(swing)

    return " ".join(sentences).strip()


def _safe_summary(event: dict[str, Any]) -> str:
    headline = ((event.get("competitions") or [{}])[0].get("notes") or [])
    if headline:
        text = headline[0].get("headline") or headline[0].get("type")
        if text:
            return str(text)
    return ""


def _biggest_run(summary: dict[str, Any]) -> str:
    """Find the biggest unanswered scoring run by either team. Return a prose sentence."""
    plays = summary.get("plays") or []
    if not plays:
        return ""

    teams = _team_ids_from_summary(summary)
    team_name = {teams.get("mystics_id", ""): "Mystics", teams.get("opponent_id", ""): teams.get("opponent_name", "Opponent")}

    best = {"team_id": None, "points": 0, "start_q": None, "start_clock": None}
    current = {"team_id": None, "points": 0, "start_q": None, "start_clock": None}

    for play in plays:
        if not play.get("scoringPlay"):
            continue
        team_id = str((play.get("team") or {}).get("id", ""))
        pts = int(play.get("scoreValue") or 0)
        if team_id == current["team_id"]:
            current["points"] += pts
        else:
            if current["points"] >= best["points"]:
                best = dict(current)
            current = {
                "team_id": team_id,
                "points": pts,
                "start_q": (play.get("period") or {}).get("number"),
                "start_clock": (play.get("clock") or {}).get("displayValue"),
            }
    if current["points"] >= best["points"]:
        best = dict(current)

    if best["points"] < 6:
        return ""
    label = team_name.get(best["team_id"]) or "An unidentified team"
    return (
        f"Biggest scoring run of the game: {label} scored {best['points']} unanswered "
        f"starting at {best['start_clock']} of Q{best['start_q']}."
    )


def _win_prob_arc(summary: dict[str, Any]) -> str:
    """Describe the Mystics' best and worst win-probability moments in one sentence."""
    wp = summary.get("winprobability") or []
    if not wp:
        return ""

    teams = _team_ids_from_summary(summary)
    mystics_home = teams.get("mystics_home_away") == "home"

    def mystics_pct(sample: dict[str, Any]) -> float:
        home = float(sample.get("homeWinPercentage") or 0.0)
        return home if mystics_home else (1.0 - home)

    pcts = [mystics_pct(s) for s in wp]
    if not pcts:
        return ""
    best = max(pcts)
    worst = min(pcts)
    if best - worst < 0.15:
        return f"Win-probability stayed flat ({worst:.0%}–{best:.0%} for the Mystics)."
    return (
        f"Mystics' win-probability range: peaked at {best:.0%} and bottomed at {worst:.0%} across the game."
    )


def _team_ids_from_summary(summary: dict[str, Any]) -> dict[str, str]:
    """Map Mystics + opponent team IDs and home/away from the summary header."""
    competitors = (summary.get("header") or {}).get("competitions", [{}])[0].get("competitors", [])
    info: dict[str, str] = {}
    for c in competitors:
        team = c.get("team") or {}
        tid = str(team.get("id") or "")
        if tid == ESPN_TEAM_ID or team.get("displayName") == TEAM_NAME:
            info["mystics_id"] = tid
            info["mystics_home_away"] = c.get("homeAway", "")
        else:
            info["opponent_id"] = tid
            info["opponent_name"] = team.get("displayName", "Opponent")
    return info


def _narrative_angles(event: dict[str, Any], summary: dict[str, Any] | None) -> list[str]:
    """Suggested editorial angles based on what the summary data revealed. NOT mandates."""
    if not summary:
        return []

    competitors = event.get("competitions", [{}])[0].get("competitors", [])
    mystics = _team_competitor(competitors)
    opponent = next((item for item in competitors if item is not mystics), {})
    opponent_name = opponent.get("team", {}).get("displayName", "the opponent")

    angles: list[str] = []
    run = _biggest_run(summary)
    if run:
        angles.append(f"Frame the result around the biggest scoring run of the game ({run.split(': ', 1)[-1].rstrip('.')}).")

    swing = _win_prob_arc(summary)
    if swing and "stayed flat" in swing:
        angles.append(f"Acknowledge that this was never a competitive game in win-probability terms vs {opponent_name}.")

    block = _mystics_boxscore_block(summary)
    if block and (block.get("statistics") or [{}])[0].get("athletes"):
        angles.append("Anchor the recap on the Mystics' boxscore leaders rather than aggregate team stats.")

    return angles[:3]
