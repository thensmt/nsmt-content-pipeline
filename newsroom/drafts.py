"""Markdown draft rendering for Mystics postgame recaps."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from newsroom.common import DEFAULT_DRAFT_DIR, DEFAULT_PACKET_DIR, TEAM_ABBR, TEAM_ID, TEAM_NAME, _display_date, _opponent_team, _selected_angle, _team_by_id
from newsroom.schemas import validate_normalized_game_packet

def render_markdown_draft(packet: dict[str, Any]) -> str:
    """Render a 600-800 word markdown recap draft from normalized facts."""
    game = packet["game"]
    narrative = packet["narrative"]
    writer = packet["writer_profile"]
    mystics = _team_by_id(game["teams"], TEAM_ID)
    opponent = _opponent_team(game["teams"])

    title = _headline(packet)
    article = _article_body(packet)
    excerpt = _excerpt(packet)
    word_count = len(re.findall(r"\b[\w'-]+\b", article))
    if not 600 <= word_count <= 800:
        raise ValueError(f"Generated recap draft is {word_count} words; expected 600-800")

    frontmatter = {
        "title": title,
        "date": game["date"][:10],
        "team": TEAM_NAME,
        "opponent": opponent["name"],
        "game_id": game["id"],
        "author": writer["name"],
        "status": "draft",
        "article_type": "postgame_recap",
        "final_score": narrative["final_score"],
        "result": narrative["result"],
        "source": "ESPN site API",
    }
    yamlish = "\n".join(f"{key}: {json.dumps(value)}" for key, value in frontmatter.items())
    source_lines = "\n".join(f"- {src['name']}: {src['url']}" for src in packet.get("sources", []))
    angles = "\n".join(
        f"- {angle['angle_title']} (confidence {angle['confidence']})"
        for angle in packet.get("story_angles", [])
    )

    return (
        f"---\n{yamlish}\n---\n\n"
        f"# {title}\n\n"
        f"**By {writer['name']}, NSMT {writer['title']}**\n\n"
        f"{article}\n\n"
        f"**Excerpt:** {excerpt}\n\n"
        f"{_editorial_notes_markdown(packet)}\n\n"
        "## Narrative Signals\n\n"
        f"- Final score: {narrative['final_score']}\n"
        f"- Biggest scoring run: {narrative['biggest_scoring_run']['summary']}\n"
        f"- Key quarter/turning point: {narrative['key_quarter_or_turning_point']['summary']}\n"
        f"- Rebounding/turnover/bench edge: {_edge_sentence(narrative['stat_edges'])}\n\n"
        "## Likely Article Angles\n\n"
        f"{angles}\n\n"
        "## Sources\n\n"
        f"{source_lines}\n"
    )


def write_outputs(
    packet: dict[str, Any],
    *,
    packet_dir: Path = DEFAULT_PACKET_DIR,
    draft_dir: Path = DEFAULT_DRAFT_DIR,
) -> tuple[Path, Path]:
    validate_normalized_game_packet(packet)
    packet_dir.mkdir(parents=True, exist_ok=True)
    draft_dir.mkdir(parents=True, exist_ok=True)

    game = packet["game"]
    packet_path = packet_dir / f"mystics_postgame_{game['id']}.json"
    draft_path = draft_dir / f"mystics-postgame-{game['date'][:10]}-{game['id']}.md"

    packet_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    draft_path.write_text(render_markdown_draft(packet) + "\n")
    return packet_path, draft_path


def _editorial_notes_markdown(packet: dict[str, Any]) -> str:
    selected = _selected_angle(packet)
    alternates = (packet.get("story_angles") or [])[1:]
    supporting = selected.get("supporting_signals") or []
    risks = selected.get("risk_flags") or []
    game = packet.get("game") or {}

    alternate_line = "; ".join(
        f"{angle.get('angle_title', 'Untitled angle')} (confidence {angle.get('confidence', '?')})"
        for angle in alternates
    ) or "None"
    supporting_line = "; ".join(str(item) for item in supporting) or "None"
    risk_line = "; ".join(str(item) for item in risks) or "None flagged."

    return (
        "## Editorial Notes\n\n"
        f"- Selected angle: {selected.get('angle_title', 'No selected angle')} "
        f"(confidence {selected.get('confidence', '?')})\n"
        f"- Alternate angles: {alternate_line}\n"
        f"- Key supporting signals: {supporting_line}\n"
        f"- Risk flags: {risk_line}\n"
        f"- Source event ID: {game.get('id', '')}\n"
        f"- Generated timestamp: {packet.get('retrieved_at', '')}"
    )


def _headline(packet: dict[str, Any]) -> str:
    game = packet["game"]
    narrative = packet["narrative"]
    opponent = _opponent_team(game["teams"])
    selected = _selected_angle(packet)
    if selected.get("angle_title", "").startswith("Possession gap"):
        return f"Mystics' possession gap defines loss to {opponent['name'].replace('Washington ', '')}"
    if selected.get("angle_title", "").endswith("recovery story"):
        return f"Mystics fall to {opponent['name'].replace('Washington ', '')} after run shifts game"
    if narrative["result"] == "win":
        return f"Mystics handle {opponent['name'].replace('Washington ', '')} behind timely scoring run"
    return f"Mystics fall to {opponent['name'].replace('Washington ', '')} as possession gap widens"


def _excerpt(packet: dict[str, Any]) -> str:
    narrative = packet["narrative"]
    return (
        f"{narrative['final_score']} as {narrative['biggest_scoring_run']['summary']} "
        f"Washington now turns to the next correction."
    )[:158]


def _article_body(packet: dict[str, Any]) -> str:
    game = packet["game"]
    narrative = packet["narrative"]
    mystics = _team_by_id(game["teams"], TEAM_ID)
    opponent = _opponent_team(game["teams"])
    result = narrative["result"]
    final_score = narrative["final_score"]
    run = narrative["biggest_scoring_run"]
    key = narrative["key_quarter_or_turning_point"]
    edges = narrative["stat_edges"]
    performers = narrative["top_performers"]
    mystics_performers = [p for p in performers if p["team"] == TEAM_NAME]
    opp_performers = [p for p in performers if p["team"] != TEAM_NAME]
    best_mystic = mystics_performers[0] if mystics_performers else {}
    second_mystic = mystics_performers[1] if len(mystics_performers) > 1 else {}
    best_opp = opp_performers[0] if opp_performers else {}
    opp_label = f"the {opponent['name']}"
    selected_angle = _selected_angle(packet)
    selected_summary = _reader_angle_summary(
        selected_angle.get("angle_summary") or "The strongest frame is the final score and team categories."
    )

    q_lines = ", ".join(
        f"{row['label']} {row.get(opponent['abbreviation'], row.get(opponent['name']))}-{row.get(TEAM_ABBR, row.get(TEAM_NAME))}"
        for row in game.get("scoring_by_quarter", [])
    )
    pbp_note = "ESPN's play-by-play feed was available" if game.get("play_by_play", {}).get("available") else "ESPN's play-by-play feed was not available"
    venue = game.get("venue") or "the arena"
    date_text = _display_date(game.get("date"))
    schedule = packet.get("schedule") or {}
    next_event = schedule.get("next_event") or {}
    next_sentence = ""
    if next_event.get("name"):
        next_sentence = f" Washington's next listed game is {next_event['name']} on {_display_date(next_event.get('date'))}."

    if result == "win":
        lead_clause = f"Washington beat {opp_label} {mystics['score']}-{opponent['score']}"
        posture = "kept enough control of the possession game to make its best stretches hold up"
        result_context = "That gave Washington room to absorb the rougher possessions without letting the game flip."
    else:
        lead_clause = f"Washington lost to {opp_label} {opponent['score']}-{mystics['score']}"
        posture = "spent too much of the night chasing the possession game"
        result_context = "That left Washington trying to answer the score and the category gaps at the same time."

    return (
        f"{lead_clause} on {date_text} at {venue}, with the final score landing at {final_score}. "
        f"The strongest Washington line came from {best_mystic.get('player', 'a Mystics starter')}, who finished with {best_mystic.get('stat_line', 'a productive all-around line')} "
        f"while shooting {best_mystic.get('fg', 'from the field')}. "
        f"{second_mystic.get('player', 'Another Washington contributor')} added {second_mystic.get('stat_line', 'needed support')}"
        f"{' on ' + second_mystic.get('fg') + ' shooting' if second_mystic.get('fg') else ''}. "
        f"Those numbers gave the Mystics a clear player entry point, but the broader frame was still direct: {selected_summary} "
        f"In practical terms, Washington {posture}. {result_context}\n\n"
        f"The quarter sheet backed up that read: {q_lines}. {key['summary']} "
        f"For Washington, that stretch mattered because it put more pressure on every empty trip and every defensive rebound that did not end the possession. "
        f"The Mystics found pockets of offense, especially when the ball moved cleanly into paint touches or catch-and-shoot looks, but the scoreboard kept asking for longer answers. "
        f"When a game takes that shape, a missed chance does not stay isolated for long. It becomes part of the next possession, the next defensive stand, and the next chance to steady the margin.\n\n"
        f"The available play-by-play added detail to the game's biggest run: {run['summary']} "
        f"The sequence was a collection of normal basketball plays, not one spectacular swing, but it pushed Washington into an early chase. "
        f"A layup, a perimeter make, another paint touch, and another three moved the scoreboard before the Mystics could slow the run. "
        f"That does not make the game about one minute, and it does not turn the result into a statement about effort or intent. "
        f"It does show how quickly the margin tightened around Washington once the team stats began pointing in the same direction. {pbp_note}.\n\n"
        f"The opponent context stayed factual. {_sentence_case(opp_label)} got a leading line from {best_opp.get('player', 'its top performer')}, who posted {best_opp.get('stat_line', 'a balanced stat line')}"
        f"{' on ' + best_opp.get('fg') + ' shooting' if best_opp.get('fg') else ''}. "
        f"That production mattered, but it was the combination of scoring, second chances, and cleaner possessions that made the game difficult for Washington to rebalance. "
        f"The Mystics did not need one more highlight as much as they needed a longer stretch where the box-score categories stopped moving away from them.\n\n"
        f"The edges explain why the game leaned the way it did. On the glass, {opp_label} finished with {edges['rebounds']['opponent']} rebounds to Washington's {edges['rebounds']['mystics']}. "
        f"The turnover column was sharper: Washington had {edges['turnovers']['mystics']} total turnovers, while {opp_label} had {edges['turnovers']['opponent']}. "
        f"Bench scoring was {edges['bench_points']['mystics']}-{edges['bench_points']['opponent']} from the Mystics' perspective, and the three-point line was {edges['three_point_makes']['mystics']} for Washington against {edges['three_point_makes']['opponent']} for {opp_label}. "
        f"None of those numbers needs extra drama. Together, they show a game in which Washington had to win too many recovery possessions just to get back to neutral.\n\n"
        f"For the Mystics, the clean takeaway is the gap between individual production and team control. "
        f"{best_mystic.get('player', 'Their top scorer')} gave Washington a line worth leading with, and the supporting production kept the night from being empty. "
        f"But the team-level gaps made that production feel more like resistance than command. "
        f"That is the difference between having a usable box score and owning enough of the game to control the margin. "
        f"Washington leaves with the run, the quarter split, and the possession categories all pointing toward the same correction: fewer empty trips, cleaner endings to defensive possessions, and more pressure created before the deficit grows.{next_sentence}"
    )


def _edge_sentence(edges: dict[str, Any]) -> str:
    return (
        f"REB edge {edges['rebounds']['edge']} ({edges['rebounds']['mystics']}-{edges['rebounds']['opponent']} WSH-opponent); "
        f"TO edge {edges['turnovers']['edge']} ({edges['turnovers']['mystics']}-{edges['turnovers']['opponent']}); "
        f"bench points {edges['bench_points']['mystics']}-{edges['bench_points']['opponent']}."
    )


def _sentence_case(value: str) -> str:
    return value[:1].upper() + value[1:] if value else value


def _reader_angle_summary(value: str) -> str:
    summary = str(value or "").strip()
    replacements = {
        "This result is best read through": "The result turned on",
        "Use ": "",
        "verified box-score line as the way into the recap": "box-score line as Washington's entry point",
    }
    for old, new in replacements.items():
        summary = summary.replace(old, new)
    return summary
