"""Season-level aggregator: pulls a team's full season from ESPN and rolls up
per-game data into season packets suitable for analytical/narrative writing.

Complements the daily story packet (one game) with a multi-game view.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from ingestion.cache import ESPN_TTL_MIN, SourceFetchError, get_cached_json, request_json


logger = logging.getLogger(__name__)


SCHEDULE_URL_TMPL = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_slug}/teams/{team_id}/schedule"
SUMMARY_URL_TMPL = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_slug}/summary?event={game_id}"


def fetch_season(
    team_id: str,
    team_name: str,
    sport: str = "basketball",
    league_slug: str = "wnba",
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Return a season-level aggregate for the team. Best-effort; gaps land in confidence_notes."""
    schedule_url = SCHEDULE_URL_TMPL.format(sport=sport, league_slug=league_slug, team_id=team_id)
    notes: list[str] = []

    try:
        schedule = get_cached_json(
            "espn",
            f"{league_slug}_schedule_{team_id}",
            ESPN_TTL_MIN,
            lambda: request_json(schedule_url),
        )
    except (SourceFetchError, ValueError) as exc:
        logger.warning("Season aggregator: schedule fetch failed: %s", exc)
        return {
            "team_id": team_id,
            "team_name": team_name,
            "played_games": [],
            "upcoming_games": [],
            "player_aggregates": [],
            "team_trends": {},
            "confidence_notes": [f"ESPN team schedule unavailable: {exc}"],
            "source_links": [],
        }

    events = schedule.get("events", []) if isinstance(schedule, dict) else []
    played_events = [e for e in events if _is_final(e)]
    upcoming_events = [e for e in events if _is_upcoming(e)]

    played_games: list[dict[str, Any]] = []
    for event in played_events:
        game_id = str(event.get("id") or "")
        if not game_id:
            continue
        summary, summary_note = _fetch_summary(game_id, sport, league_slug)
        if summary_note:
            notes.append(summary_note)
        played_games.append(_parse_played_game(event, summary, team_id, team_name))

    upcoming_games = [_parse_upcoming(event, team_id) for event in upcoming_events[:5]]

    player_aggregates = _player_aggregates(played_games)
    team_trends = _team_trends(played_games)
    record = _compute_record(played_games)

    return {
        "team_id": team_id,
        "team_name": team_name,
        "league": league_slug.upper(),
        "season_year": _season_year(schedule),
        "record": record,
        "played_games": played_games,
        "upcoming_games": upcoming_games,
        "player_aggregates": player_aggregates,
        "team_trends": team_trends,
        "confidence_notes": notes,
        "source_links": [
            {
                "source_name": "ESPN team schedule",
                "source_url": schedule_url,
                "retrieved_at": retrieved_at or _iso_now(),
                "confidence": 0.9,
            }
        ],
    }


def _fetch_summary(game_id: str, sport: str, league_slug: str) -> tuple[dict[str, Any] | None, str]:
    url = SUMMARY_URL_TMPL.format(sport=sport, league_slug=league_slug, game_id=game_id)
    try:
        payload = get_cached_json(
            "espn",
            f"{league_slug}_summary_{game_id}",
            ESPN_TTL_MIN,
            lambda: request_json(url),
        )
    except (SourceFetchError, ValueError) as exc:
        logger.warning("Season aggregator: summary %s fetch failed: %s", game_id, exc)
        return None, f"ESPN summary unavailable for game {game_id}: {exc}"
    return (payload if isinstance(payload, dict) else None), ""


def _is_final(event: dict[str, Any]) -> bool:
    status = ((event.get("competitions") or [{}])[0].get("status") or {}).get("type", {})
    return status.get("completed") is True or status.get("name") == "STATUS_FINAL"


def _is_upcoming(event: dict[str, Any]) -> bool:
    status = ((event.get("competitions") or [{}])[0].get("status") or {}).get("type", {})
    return status.get("name") == "STATUS_SCHEDULED"


def _parse_played_game(event: dict[str, Any], summary: dict[str, Any] | None, team_id: str, team_name: str) -> dict[str, Any]:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors") or []
    self_comp = next((c for c in competitors if str((c.get("team") or {}).get("id")) == team_id), {})
    opp_comp = next((c for c in competitors if c is not self_comp), {})

    self_score = _coerce_score(self_comp.get("score"))
    opp_score = _coerce_score(opp_comp.get("score"))
    home_away = self_comp.get("homeAway", "")
    opponent_name = (opp_comp.get("team") or {}).get("displayName", "Opponent")
    won = bool(self_comp.get("winner"))

    result = f"{'W' if won else 'L'} {self_score}-{opp_score}"

    out: dict[str, Any] = {
        "game_id": str(event.get("id") or ""),
        "date": str(event.get("date") or "")[:10],
        "opponent": opponent_name,
        "home_away": home_away,
        "result": result,
        "self_score": self_score,
        "opponent_score": opp_score,
        "venue": (competition.get("venue") or {}).get("fullName", ""),
    }

    if summary:
        out["boxscore"] = _boxscore_rows(summary, team_id)
        out["attendance"] = _attendance(summary)
        out["linescore"] = _linescore(summary)
        out["narrative_beats"] = _narrative_beats(summary, team_id)
        out["win_prob_arc"] = _win_prob_arc(summary, home_away)
    else:
        out["boxscore"] = []
        out["attendance"] = 0
        out["linescore"] = ""
        out["narrative_beats"] = []
        out["win_prob_arc"] = ""

    return out


def _parse_upcoming(event: dict[str, Any], team_id: str) -> dict[str, Any]:
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors") or []
    self_comp = next((c for c in competitors if str((c.get("team") or {}).get("id")) == team_id), {})
    opp_comp = next((c for c in competitors if c is not self_comp), {})
    return {
        "game_id": str(event.get("id") or ""),
        "date": str(event.get("date") or "")[:10],
        "opponent": (opp_comp.get("team") or {}).get("displayName", "Opponent"),
        "home_away": self_comp.get("homeAway", ""),
        "venue": (competition.get("venue") or {}).get("fullName", ""),
    }


def _boxscore_rows(summary: dict[str, Any], team_id: str) -> list[dict[str, Any]]:
    """Parse Mystics boxscore rows: one per player with stats parsed into structured fields."""
    block = _team_box_block(summary, team_id)
    if not block:
        return []
    stats_block = (block.get("statistics") or [{}])[0]
    labels = stats_block.get("labels") or []
    if not labels:
        return []
    rows: list[dict[str, Any]] = []
    idx = {label: i for i, label in enumerate(labels)}

    def _s(stats: list[Any], label: str) -> str:
        i = idx.get(label)
        if i is None or i >= len(stats):
            return ""
        return str(stats[i] or "")

    for entry in stats_block.get("athletes") or []:
        if not entry.get("active", True) and not entry.get("stats"):
            continue
        stats = entry.get("stats") or []
        if not stats:
            continue
        athlete = entry.get("athlete") or {}
        name = athlete.get("displayName")
        if not name:
            continue
        rows.append(
            {
                "player": name,
                "jersey": athlete.get("jersey", ""),
                "min": _coerce_int(_s(stats, "MIN")),
                "pts": _coerce_int(_s(stats, "PTS")),
                "reb": _coerce_int(_s(stats, "REB")),
                "ast": _coerce_int(_s(stats, "AST")),
                "stl": _coerce_int(_s(stats, "STL")),
                "blk": _coerce_int(_s(stats, "BLK")),
                "to": _coerce_int(_s(stats, "TO")),
                "fg": _s(stats, "FG"),
                "three": _s(stats, "3PT"),
                "ft": _s(stats, "FT"),
                "plus_minus": _coerce_int(_s(stats, "+/-")),
            }
        )
    return rows


def _team_box_block(summary: dict[str, Any], team_id: str) -> dict[str, Any]:
    for block in (summary.get("boxscore") or {}).get("players") or []:
        if str((block.get("team") or {}).get("id")) == team_id:
            return block
    return {}


def _attendance(summary: dict[str, Any]) -> int:
    val = (summary.get("gameInfo") or {}).get("attendance")
    return val if isinstance(val, int) and val > 0 else 0


def _linescore(summary: dict[str, Any]) -> str:
    competitors = (summary.get("header") or {}).get("competitions", [{}])[0].get("competitors", [])
    parts = []
    for c in competitors:
        abbr = (c.get("team") or {}).get("abbreviation", "")
        scores = [str((ls or {}).get("displayValue", "")) for ls in (c.get("linescores") or [])]
        if abbr and scores:
            parts.append(f"{abbr}: {'-'.join(scores)}")
    return " | ".join(parts)


def _narrative_beats(summary: dict[str, Any], team_id: str) -> list[str]:
    """Concise 1-3 beats per game: biggest run, lead changes count, biggest deficit."""
    plays = summary.get("plays") or []
    if not plays:
        return []
    beats: list[str] = []

    # Biggest unanswered run by either team
    best = {"team_id": None, "points": 0, "start_q": None, "start_clock": None}
    current = {"team_id": None, "points": 0, "start_q": None, "start_clock": None}
    for play in plays:
        if not play.get("scoringPlay"):
            continue
        tid = str((play.get("team") or {}).get("id", ""))
        pts = int(play.get("scoreValue") or 0)
        if tid == current["team_id"]:
            current["points"] += pts
        else:
            if current["points"] > best["points"]:
                best = dict(current)
            current = {
                "team_id": tid,
                "points": pts,
                "start_q": (play.get("period") or {}).get("number"),
                "start_clock": (play.get("clock") or {}).get("displayValue"),
            }
    if current["points"] > best["points"]:
        best = dict(current)
    if best["points"] >= 6:
        run_by = "Mystics" if best["team_id"] == team_id else "Opponent"
        beats.append(f"{run_by} hit a {best['points']}-0 run starting at {best['start_clock']} of Q{best['start_q']}.")

    # Biggest deficit Mystics faced
    deficits = []
    for play in plays:
        if "homeScore" not in play or "awayScore" not in play:
            continue
        # Determine which side Mystics are on (need home/away of Mystics)
        # Look at any scoring play to determine — but easier from competitors
    home_id, away_id = _home_away_ids(summary)
    mystics_home = home_id == team_id
    max_deficit = 0
    for play in plays:
        if "homeScore" not in play:
            continue
        hs = int(play.get("homeScore") or 0)
        aws = int(play.get("awayScore") or 0)
        deficit = (aws - hs) if mystics_home else (hs - aws)
        if deficit > max_deficit:
            max_deficit = deficit
    if max_deficit >= 8:
        beats.append(f"Mystics faced a maximum deficit of {max_deficit} points in this game.")

    return beats


def _win_prob_arc(summary: dict[str, Any], home_away: str) -> str:
    wp = summary.get("winprobability") or []
    if not wp:
        return ""
    pcts = []
    for s in wp:
        home = float(s.get("homeWinPercentage") or 0.0)
        pcts.append(home if home_away == "home" else (1.0 - home))
    if not pcts:
        return ""
    best = max(pcts)
    worst = min(pcts)
    return f"Mystics win-prob range: peak {best:.0%}, low {worst:.0%}."


def _home_away_ids(summary: dict[str, Any]) -> tuple[str, str]:
    competitors = (summary.get("header") or {}).get("competitions", [{}])[0].get("competitors", [])
    home = away = ""
    for c in competitors:
        tid = str((c.get("team") or {}).get("id", ""))
        if c.get("homeAway") == "home":
            home = tid
        elif c.get("homeAway") == "away":
            away = tid
    return home, away


def _player_aggregates(played_games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-player season averages, sorted by composite (PPG + 0.5*RPG + APG)."""
    by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for g in played_games:
        for row in g.get("boxscore") or []:
            by_player[row["player"]].append({**row, "_date": g["date"], "_result": g["result"]})

    aggregates = []
    for player, rows in by_player.items():
        games = len(rows)
        if games == 0:
            continue
        ppg = sum(r["pts"] for r in rows) / games
        rpg = sum(r["reb"] for r in rows) / games
        apg = sum(r["ast"] for r in rows) / games
        spg = sum(r["stl"] for r in rows) / games
        bpg = sum(r["blk"] for r in rows) / games
        mpg = sum(r["min"] for r in rows) / games
        best_game = max(rows, key=lambda r: r["pts"] + 0.5 * r["reb"] + r["ast"])
        aggregates.append(
            {
                "player": player,
                "games": games,
                "ppg": round(ppg, 1),
                "rpg": round(rpg, 1),
                "apg": round(apg, 1),
                "spg": round(spg, 1),
                "bpg": round(bpg, 1),
                "mpg": round(mpg, 1),
                "best_game": {
                    "date": best_game["_date"],
                    "result": best_game["_result"],
                    "stat_line": f"{best_game['pts']} PTS, {best_game['reb']} REB, {best_game['ast']} AST, {best_game['fg']} FG",
                },
                "composite": round(ppg + 0.5 * rpg + apg, 2),
            }
        )
    aggregates.sort(key=lambda a: a["composite"], reverse=True)
    return aggregates


def _team_trends(played_games: list[dict[str, Any]]) -> dict[str, Any]:
    if not played_games:
        return {}
    home = [g for g in played_games if g["home_away"] == "home"]
    away = [g for g in played_games if g["home_away"] == "away"]
    pf = sum(g["self_score"] for g in played_games) / len(played_games)
    pa = sum(g["opponent_score"] for g in played_games) / len(played_games)
    home_wl = f"{sum(1 for g in home if g['result'].startswith('W'))}-{sum(1 for g in home if g['result'].startswith('L'))}"
    away_wl = f"{sum(1 for g in away if g['result'].startswith('W'))}-{sum(1 for g in away if g['result'].startswith('L'))}"
    return {
        "ppg_offense": round(pf, 1),
        "ppg_defense": round(pa, 1),
        "scoring_margin": round(pf - pa, 1),
        "home_wl": home_wl,
        "away_wl": away_wl,
        "games_played": len(played_games),
    }


def _compute_record(played_games: list[dict[str, Any]]) -> str:
    wins = sum(1 for g in played_games if g["result"].startswith("W"))
    losses = sum(1 for g in played_games if g["result"].startswith("L"))
    return f"{wins}-{losses}"


def _season_year(schedule: dict[str, Any]) -> int:
    season = schedule.get("season") or {}
    year = season.get("year") or schedule.get("requestedSeason", {}).get("year")
    try:
        return int(year) if year else date.today().year
    except (TypeError, ValueError):
        return date.today().year


def _coerce_int(value: Any) -> int:
    try:
        if isinstance(value, str):
            return int(float(value))
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _coerce_score(value: Any) -> int:
    """ESPN scores can be a dict {value, displayValue} or a plain number/string."""
    if isinstance(value, dict):
        v = value.get("value")
        if v is not None:
            return _coerce_int(v)
        return _coerce_int(value.get("displayValue"))
    return _coerce_int(value)


def _iso_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
