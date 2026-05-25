"""Story angle selection and narrative signal extraction for Mystics recaps."""

from __future__ import annotations

import re
from typing import Any

from newsroom.common import TEAM_ABBR, TEAM_ID, TEAM_NAME, _confidence, _dedupe_strings, _opponent_team, _team_by_id, _to_int
from newsroom.memory import _default_memory_risk_flags, _memory_item, _player_profile, load_mystics_memory
from newsroom.schemas import validate_story_angles

def extract_narrative_signals(packet: dict[str, Any]) -> dict[str, Any]:
    game = packet["game"]
    mystics = _team_by_id(game["teams"], TEAM_ID)
    opponent = _opponent_team(game["teams"])
    result = "win" if mystics.get("winner") else "loss"

    run = _biggest_scoring_run(game.get("play_by_play", {}).get("scoring_plays", []), game["teams"])
    key_quarter = _key_quarter(game.get("scoring_by_quarter", []), result)
    edges = _stat_edges(mystics, opponent)
    top_performers = _top_performers(game["teams"])
    angles = _article_angles(result, opponent, run, key_quarter, edges, top_performers)

    final_score = _final_score_text(game["teams"])
    return {
        "final_score": final_score,
        "result": result,
        "top_performers": top_performers[:6],
        "biggest_scoring_run": run,
        "key_quarter_or_turning_point": key_quarter,
        "stat_edges": edges,
        "likely_article_angles": angles,
    }


def select_story_angles(packet: dict[str, Any]) -> list[dict[str, Any]]:
    """Return exactly three ranked story angles from game facts + memory context."""
    game = packet["game"]
    narrative = packet.get("narrative") or extract_narrative_signals(packet)
    memory = packet.get("memory") or load_mystics_memory()
    mystics = _team_by_id(game["teams"], TEAM_ID)
    opponent = _opponent_team(game["teams"])
    margin = abs(int(opponent.get("score") or 0) - int(mystics.get("score") or 0))
    result = narrative.get("result", "loss")
    top_mystics = [p for p in narrative.get("top_performers", []) if p.get("team") == TEAM_NAME]
    top_opponents = [p for p in narrative.get("top_performers", []) if p.get("team") != TEAM_NAME]
    best_mystic = top_mystics[0] if top_mystics else {}
    best_opponent = top_opponents[0] if top_opponents else {}
    run = narrative.get("biggest_scoring_run") or {}
    key_quarter = narrative.get("key_quarter_or_turning_point") or {}
    edges = narrative.get("stat_edges") or {}
    play_by_play = game.get("play_by_play") or {}
    gamecast = game.get("gamecast") or {}

    angles = [
        _possession_angle(narrative, memory, opponent, margin, edges),
        _run_quarter_angle(narrative, memory, opponent, margin, run, key_quarter, play_by_play, gamecast),
        _performer_angle(narrative, memory, result, margin, best_mystic, best_opponent),
    ]
    angles.sort(key=lambda item: item["confidence"], reverse=True)
    return validate_story_angles(angles[:3])


def _possession_angle(
    narrative: dict[str, Any],
    memory: dict[str, Any],
    opponent: dict[str, Any],
    margin: int,
    edges: dict[str, Any],
) -> dict[str, Any]:
    season = _memory_item(memory, "season_narratives", "narratives", "possession-discipline")
    storyline = _memory_item(memory, "recent_storylines", "storylines", "stat-with-restraint")
    risk_flags = _default_memory_risk_flags(memory)
    risk_flags.extend(season.get("risk_flags") or [])
    risk_flags.extend(storyline.get("risk_flags") or [])
    support = [
        f"Final score: {narrative.get('final_score')}",
        f"Scoring margin: {margin}",
        _edge_signal("Rebounds", edges.get("rebounds")),
        _edge_signal("Turnovers", edges.get("turnovers")),
        _edge_signal("Bench points", edges.get("bench_points")),
        _edge_signal("3PT", edges.get("three_point_makes")),
    ]
    if season.get("label"):
        support.append(f"Memory context: {season['label']} - {season.get('context', '')}")
    support = _clean_signal_list(support)

    missing_stats = [label for label, edge in (edges or {}).items() if not isinstance(edge, dict) or edge.get("mystics") is None]
    if missing_stats:
        risk_flags.append(f"Some team-stat edges are incomplete: {', '.join(sorted(missing_stats))}.")
    confidence = 0.62
    confidence += 0.1 if margin >= 10 else 0.03
    confidence += 0.08 if len(support) >= 5 else 0.0
    confidence += 0.05 if not missing_stats else -0.12
    return {
        "angle_title": "Possession gap defined Washington's chase",
        "angle_summary": (
            f"This result is best read through possession math: turnovers, rebounds, "
            f"bench scoring, and 3-point volume gave the {opponent['name']} "
            "more ways to control the game."
        ),
        "confidence": _confidence(confidence),
        "supporting_signals": support,
        "risk_flags": _dedupe_strings(risk_flags),
    }


def _run_quarter_angle(
    narrative: dict[str, Any],
    memory: dict[str, Any],
    opponent: dict[str, Any],
    margin: int,
    run: dict[str, Any],
    key_quarter: dict[str, Any],
    play_by_play: dict[str, Any],
    gamecast: dict[str, Any],
) -> dict[str, Any]:
    season = _memory_item(memory, "season_narratives", "narratives", "quarter-response")
    storyline = _memory_item(memory, "recent_storylines", "storylines", "chase-game")
    risk_flags = _default_memory_risk_flags(memory)
    risk_flags.extend(season.get("risk_flags") or [])
    risk_flags.extend(storyline.get("risk_flags") or [])
    if not play_by_play.get("available"):
        risk_flags.append("Play-by-play unavailable; avoid describing possession sequence beyond quarter totals.")
    if not run.get("points"):
        risk_flags.append("No meaningful scoring run was detected; keep the angle tied to quarter scoring.")

    support = [
        f"Final score: {narrative.get('final_score')}",
        f"Scoring margin: {margin}",
        f"Biggest run: {run.get('summary', '')}",
        f"Key quarter: {key_quarter.get('summary', '')}",
        f"Gamecast/play-by-play available: {bool(play_by_play.get('available'))}",
        f"Win probability samples: {gamecast.get('win_probability_samples', 0)}",
    ]
    if season.get("label"):
        support.append(f"Memory context: {season['label']} - {season.get('context', '')}")
    support = _clean_signal_list(support)

    confidence = 0.55
    confidence += 0.14 if play_by_play.get("available") else -0.12
    confidence += 0.08 if int(run.get("points") or 0) >= 6 else 0.0
    confidence += 0.05 if abs(int(key_quarter.get("impact") or 0)) >= 8 else 0.0
    return {
        "angle_title": f"{opponent['name']} run turned the recap into a recovery story",
        "angle_summary": (
            f"The scoring run and the key quarter stretched the game, then Washington spent "
            f"the rest of the night chasing against the {opponent['name']}."
        ),
        "confidence": _confidence(confidence),
        "supporting_signals": support,
        "risk_flags": _dedupe_strings(risk_flags),
    }


def _performer_angle(
    narrative: dict[str, Any],
    memory: dict[str, Any],
    result: str,
    margin: int,
    best_mystic: dict[str, Any],
    best_opponent: dict[str, Any],
) -> dict[str, Any]:
    player_name = best_mystic.get("player") or "Washington's top performer"
    profile = _player_profile(memory, player_name)
    risk_flags = _default_memory_risk_flags(memory)
    risk_flags.extend(profile.get("avoid") or [])
    if result == "loss" and margin >= 10:
        risk_flags.append("Individual-performance angle is secondary because Washington lost by double digits.")
    if not profile:
        risk_flags.append(f"No memory profile found for {player_name}; avoid role or background claims.")

    support = [
        f"Final score: {narrative.get('final_score')}",
        f"Top Mystics performer: {player_name} - {best_mystic.get('stat_line', 'stat line unavailable')}",
        f"Top opponent performer: {best_opponent.get('player', 'opponent leader unavailable')} - {best_opponent.get('stat_line', 'stat line unavailable')}",
    ]
    if profile.get("editorial_lens"):
        support.append(f"Memory context: {profile['editorial_lens']}")
    support = _clean_signal_list(support)

    confidence = 0.5
    confidence += 0.08 if profile else 0.0
    confidence += 0.05 if int(best_mystic.get("points") or 0) >= 12 else 0.0
    confidence += 0.05 if result == "win" else -0.05
    confidence += -0.06 if margin >= 15 and result == "loss" else 0.0
    return {
        "angle_title": f"{player_name}'s production as the human-scale entry point",
        "angle_summary": (
            f"Use {player_name}'s verified box-score line as the way into the recap, "
            "while keeping the team result and possession gaps in control of the conclusion."
        ),
        "confidence": _confidence(confidence),
        "supporting_signals": support,
        "risk_flags": _dedupe_strings(risk_flags),
    }


def _final_score_text(teams: list[dict[str, Any]]) -> str:
    home = next((team for team in teams if team.get("home_away") == "home"), None)
    away = next((team for team in teams if team.get("home_away") == "away"), None)
    if home and away:
        first, second = (home, away) if home["score"] >= away["score"] else (away, home)
        return f"{first['name']} {first['score']}, {second['name']} {second['score']}"
    ordered = sorted(teams, key=lambda team: int(team.get("score") or 0), reverse=True)
    return ", ".join(f"{team['name']} {team['score']}" for team in ordered)


def _biggest_scoring_run(scoring_plays: list[dict[str, Any]], teams: list[dict[str, Any]]) -> dict[str, Any]:
    team_names = {team["id"]: team["name"] for team in teams}
    best: dict[str, Any] = {"team_id": "", "points": 0, "plays": []}
    current: dict[str, Any] = {"team_id": "", "points": 0, "plays": []}

    for play in scoring_plays:
        team_id = str(play.get("team_id") or "")
        points = int(play.get("score_value") or 0)
        if not team_id or points <= 0:
            continue
        if current["team_id"] == team_id:
            current["points"] += points
            current["plays"].append(play)
        else:
            if current["points"] > best["points"]:
                best = {"team_id": current["team_id"], "points": current["points"], "plays": list(current["plays"])}
            current = {"team_id": team_id, "points": points, "plays": [play]}
    if current["points"] > best["points"]:
        best = {"team_id": current["team_id"], "points": current["points"], "plays": list(current["plays"])}

    plays = best.get("plays") or []
    first = plays[0] if plays else {}
    last = plays[-1] if plays else {}
    team = team_names.get(best.get("team_id"), "Unknown team")
    points = int(best.get("points") or 0)
    summary = "Play-by-play did not expose a meaningful scoring run."
    if points:
        summary = (
            f"{team} scored {points} unanswered from {first.get('clock', '')} "
            f"to {last.get('clock', '')} of the {last.get('period_label') or 'game'}."
        )
    return {
        "team": team,
        "team_id": best.get("team_id") or "",
        "points": points,
        "start_period": first.get("period"),
        "start_clock": first.get("clock") or "",
        "end_period": last.get("period"),
        "end_clock": last.get("clock") or "",
        "summary": summary,
        "plays": plays,
    }


def _key_quarter(scoring_by_quarter: list[dict[str, Any]], result: str) -> dict[str, Any]:
    best = None
    for row in scoring_by_quarter:
        mystics_pts = _to_int(row.get(TEAM_NAME) if TEAM_NAME in row else row.get(TEAM_ABBR)) or 0
        opp_name = next((key for key in row if key not in {"period", "label", TEAM_NAME, TEAM_ABBR} and len(key) > 3), "")
        opp_pts = _to_int(row.get(opp_name)) or 0
        margin = mystics_pts - opp_pts
        impact = margin if result == "win" else -margin
        candidate = {
            "period": row.get("period"),
            "label": row.get("label") or "",
            "mystics_points": mystics_pts,
            "opponent_points": opp_pts,
            "opponent": opp_name,
            "margin": margin,
            "impact": impact,
        }
        if best is None or candidate["impact"] > best["impact"]:
            best = candidate
    if not best:
        return {"summary": "Quarter scoring was unavailable."}
    if result == "win":
        summary = (
            f"Washington's clearest quarter was {best['label']}, when it won the period "
            f"{best['mystics_points']}-{best['opponent_points']}."
        )
    else:
        summary = (
            f"The game tilted hardest in {best['label']}, when {best['opponent']} "
            f"outscored Washington {best['opponent_points']}-{best['mystics_points']}."
        )
    best["summary"] = summary
    return best


def _stat_edges(mystics: dict[str, Any], opponent: dict[str, Any]) -> dict[str, Any]:
    edges = {
        "rebounds": _edge_from_team_stats(mystics, opponent, "Rebounds"),
        "turnovers": _turnover_edge(mystics, opponent),
        "bench_points": _bench_points_edge(mystics, opponent),
        "points_in_paint": _edge_from_team_stats(mystics, opponent, "Points in Paint"),
        "three_point_makes": _made_attempt_edge(mystics, opponent, "3PT"),
    }
    return edges


def _edge_from_team_stats(mystics: dict[str, Any], opponent: dict[str, Any], stat_label: str) -> dict[str, Any]:
    m_val = _to_int((mystics.get("team_stats") or {}).get(stat_label))
    o_val = _to_int((opponent.get("team_stats") or {}).get(stat_label))
    holder = TEAM_NAME if (m_val or 0) > (o_val or 0) else opponent["name"] if (o_val or 0) > (m_val or 0) else "Even"
    return {"mystics": m_val, "opponent": o_val, "edge": holder}


def _turnover_edge(mystics: dict[str, Any], opponent: dict[str, Any]) -> dict[str, Any]:
    m_val = _to_int((mystics.get("team_stats") or {}).get("Total Turnovers"))
    o_val = _to_int((opponent.get("team_stats") or {}).get("Total Turnovers"))
    if m_val is None:
        m_val = _to_int((mystics.get("team_stats") or {}).get("Turnovers"))
    if o_val is None:
        o_val = _to_int((opponent.get("team_stats") or {}).get("Turnovers"))
    holder = TEAM_NAME if (m_val or 0) < (o_val or 0) else opponent["name"] if (o_val or 0) < (m_val or 0) else "Even"
    return {"mystics": m_val, "opponent": o_val, "edge": holder, "lower_is_better": True}


def _bench_points_edge(mystics: dict[str, Any], opponent: dict[str, Any]) -> dict[str, Any]:
    m_val = sum(int(row.get("points") or 0) for row in mystics.get("box_score", []) if not row.get("starter"))
    o_val = sum(int(row.get("points") or 0) for row in opponent.get("box_score", []) if not row.get("starter"))
    holder = TEAM_NAME if m_val > o_val else opponent["name"] if o_val > m_val else "Even"
    return {"mystics": m_val, "opponent": o_val, "edge": holder}


def _made_attempt_edge(mystics: dict[str, Any], opponent: dict[str, Any], stat_label: str) -> dict[str, Any]:
    m_text = (mystics.get("team_stats") or {}).get(stat_label, "")
    o_text = (opponent.get("team_stats") or {}).get(stat_label, "")
    m_made = _made_from_pair(m_text)
    o_made = _made_from_pair(o_text)
    holder = TEAM_NAME if m_made > o_made else opponent["name"] if o_made > m_made else "Even"
    return {"mystics": m_text, "opponent": o_text, "edge": holder}


def _made_from_pair(value: Any) -> int:
    match = re.match(r"^\s*(\d+)\s*[-/]", str(value or ""))
    return int(match.group(1)) if match else 0


def _top_performers(teams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    performers = []
    for team in teams:
        for row in team.get("box_score", []):
            if row.get("did_not_play"):
                continue
            points = int(row.get("points") or 0)
            rebounds = int(row.get("rebounds") or 0)
            assists = int(row.get("assists") or 0)
            score = points + 0.6 * rebounds + assists
            if points == 0 and rebounds == 0 and assists == 0:
                continue
            performers.append(
                {
                    "player": row["player"],
                    "team": team["name"],
                    "points": points,
                    "rebounds": rebounds,
                    "assists": assists,
                    "fg": row.get("fg") or "",
                    "three_pt": row.get("three_pt") or "",
                    "starter": bool(row.get("starter")),
                    "_score": score,
                }
            )
    performers.sort(key=lambda row: row["_score"], reverse=True)
    for row in performers:
        row.pop("_score", None)
        row["stat_line"] = _format_stat_line(row["points"], row["rebounds"], row["assists"])
    return performers


def _format_stat_line(points: int, rebounds: int, assists: int) -> str:
    return (
        f"{points} {_plural(points, 'point')}, "
        f"{rebounds} {_plural(rebounds, 'rebound')}, "
        f"{assists} {_plural(assists, 'assist')}"
    )


def _plural(value: int, label: str) -> str:
    return label if value == 1 else f"{label}s"


def _edge_signal(label: str, edge: Any) -> str:
    if not isinstance(edge, dict):
        return ""
    return f"{label}: Washington {edge.get('mystics')} vs opponent {edge.get('opponent')} (edge: {edge.get('edge')})"


def _clean_signal_list(values: list[str]) -> list[str]:
    return _dedupe_strings([value.strip() for value in values if isinstance(value, str) and value.strip()])


def _article_angles(
    result: str,
    opponent: dict[str, Any],
    run: dict[str, Any],
    key_quarter: dict[str, Any],
    edges: dict[str, Any],
    performers: list[dict[str, Any]],
) -> list[str]:
    mystics_performers = [p for p in performers if p["team"] == TEAM_NAME]
    best_mystic = mystics_performers[0]["player"] if mystics_performers else "Washington's top option"
    if result == "win":
        return [
            f"How Washington's best stretch, led by {best_mystic}, created enough separation against {opponent['name']}.",
            f"The possession story: {key_quarter.get('summary', 'one quarter shaped the game')}",
            f"Why the {edges['bench_points']['edge']} bench scoring edge mattered in a finished game.",
        ]
    run_article = _indefinite_article_for_number(run.get("points", 0))
    return [
        f"How {run_article} {run.get('points', 0)}-point {opponent['name']} run exposed Washington's margin for error.",
        f"The possession math behind the loss: turnovers, rebounds, and 3-point volume all pulled at the recap.",
        f"What {best_mystic}'s line says about the Mystics' offense when the team is chasing the game.",
    ]


def _indefinite_article_for_number(value: Any) -> str:
    text = str(value)
    return "an" if text.startswith(("8", "11", "18")) else "a"
