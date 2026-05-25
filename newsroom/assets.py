"""Secondary editorial asset generation for Mystics recaps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ingestion.cache import iso_utc
from newsroom.common import (
    DEFAULT_ASSET_DIR,
    MAYA_BROOKS_PROFILE,
    TEAM_ID,
    TEAM_NAME,
    _confidence,
    _dedupe_strings,
    _display_date,
    _display_path,
    _editorial_rules,
    _opponent_team,
    _risk_summary,
    _selected_angle,
    _team_by_id,
    _word_count,
)
from newsroom.drafts import _headline, _reader_angle_summary
from newsroom.schemas import validate_asset_index

def generate_editorial_assets(packet: dict[str, Any]) -> dict[str, Any]:
    """Generate secondary editorial assets from the selected story angle."""
    assets = {
        "short_recap": render_short_recap_asset(packet),
        "takeaways": render_takeaway_assets(packet),
        "push_alert": render_push_alert_asset(packet),
        "newsletter_blurb": render_newsletter_blurb_asset(packet),
        "seo_summary": render_seo_summary_asset(packet),
        "social_caption": render_social_caption_asset(packet),
        "headline_candidates": generate_headline_candidates(packet),
    }
    _validate_editorial_assets(assets)
    return assets


def render_short_recap_asset(packet: dict[str, Any]) -> str:
    """Render a 120-180 word fast postgame recap."""
    game = packet["game"]
    narrative = packet["narrative"]
    mystics = _team_by_id(game["teams"], TEAM_ID)
    opponent = _opponent_team(game["teams"])
    selected = _selected_angle(packet)
    key = narrative.get("key_quarter_or_turning_point") or {}
    edges = narrative.get("stat_edges") or {}
    best_mystic = _best_mystics_performer(packet)
    score = _team_score_text(mystics, opponent)
    result_word = "beat" if narrative.get("result") == "win" else "lost to"
    venue = game.get("venue") or "the listed arena"
    angle_summary = _reader_angle_summary(selected.get("angle_summary") or "The scoreboard and team categories drove the story.")

    return (
        f"Washington {result_word} the {opponent['name']} {score} on {_display_date(game.get('date'))} "
        f"at {venue}, and the clearest postgame frame was direct: "
        f"{angle_summary} "
        f"The final was {narrative.get('final_score')}. {key.get('summary', 'Quarter scoring was unavailable.')} "
        f"Washington got a clear player entry from {best_mystic.get('player', 'its top performer')}, who finished with "
        f"{best_mystic.get('stat_line', 'a listed box-score line')}, but the team-level categories kept pulling the story "
        f"back to the same place: {edges.get('turnovers', {}).get('mystics', 'unknown')} Mystics turnovers, "
        f"a {edges.get('rebounds', {}).get('mystics', 'unknown')}-{edges.get('rebounds', {}).get('opponent', 'unknown')} "
        f"rebounding split, and a bench-scoring line of {edges.get('bench_points', {}).get('mystics', 'unknown')}-"
        f"{edges.get('bench_points', {}).get('opponent', 'unknown')} from Washington's side. "
        "The clean read stays with the scoreboard, box score, and available play-by-play."
    )


def render_takeaway_assets(packet: dict[str, Any]) -> list[dict[str, str]]:
    """Render exactly three title/explanation takeaway bullets."""
    narrative = packet["narrative"]
    selected = _selected_angle(packet)
    key = narrative.get("key_quarter_or_turning_point") or {}
    run = narrative.get("biggest_scoring_run") or {}
    best_mystic = _best_mystics_performer(packet)
    player_name = best_mystic.get("player") or "Washington's top performer"
    angle_summary = _reader_angle_summary(selected.get("angle_summary") or "The team categories were the cleanest way into the game")

    return [
        {
            "title": "Possession math set the frame",
            "explanation": (
                f"{angle_summary} "
                "Rebounds, turnovers, bench scoring, and 3-point volume gave the result its clearest shape."
            ),
        },
        {
            "title": "The key stretch shaped the chase",
            "explanation": (
                f"{key.get('summary', 'Quarter scoring was unavailable.')} "
                f"{run.get('summary', 'Play-by-play did not expose a meaningful scoring run.')} "
                "That was enough scoreboard pressure to make every Washington response matter."
            ),
        },
        {
            "title": "Washington's best line still needs context",
            "explanation": (
                f"{player_name} finished with "
                f"{best_mystic.get('stat_line', 'a listed box-score line')}. "
                "That gave the Mystics a human entry point, while the final score and team gaps kept the framing balanced."
            ),
        },
    ]


def render_push_alert_asset(packet: dict[str, Any]) -> str:
    """Render a max-160 character push alert."""
    final_score = packet["narrative"].get("final_score", "Final score unavailable")
    phrase = _asset_angle_phrase(packet, compact=True)
    alert = f"Final: {final_score}. {phrase}"
    if len(alert) <= 160:
        return alert

    game = packet["game"]
    mystics = _team_by_id(game["teams"], TEAM_ID)
    opponent = _opponent_team(game["teams"])
    compact_score = f"{opponent['abbreviation']} {opponent['score']}, WSH {mystics['score']}"
    if packet["narrative"].get("result") == "win":
        compact_score = f"WSH {mystics['score']}, {opponent['abbreviation']} {opponent['score']}"
    fallback = f"Final: {compact_score}. {_asset_angle_phrase(packet, compact=True)}"
    return fallback[:160].rstrip(" .,")


def render_newsletter_blurb_asset(packet: dict[str, Any]) -> str:
    """Render a 75-120 word conversational newsletter blurb."""
    game = packet["game"]
    narrative = packet["narrative"]
    opponent = _opponent_team(game["teams"])
    selected = _selected_angle(packet)
    best_mystic = _best_mystics_performer(packet)
    player_name = best_mystic.get("player") or "Washington's top performer"

    return (
        f"The fast read from Mystics-{opponent['name'].replace('Washington ', '')}: "
        f"{narrative.get('final_score')}. Maya Brooks' full recap starts with "
        f"{selected.get('angle_title', 'the main postgame angle')}. "
        f"That means the piece leans into the scoreboard, possession categories, and {player_name}'s "
        "box-score line while keeping the opponent context grounded. It is built for readers who want "
        "the postgame feel and a clear explanation of how the game moved. The focus stays on Washington's "
        "response, the quarter that changed the margin, and the numbers that made the final score hold."
    )


def render_seo_summary_asset(packet: dict[str, Any]) -> str:
    """Render a readable one-paragraph SEO summary."""
    game = packet["game"]
    narrative = packet["narrative"]
    opponent = _opponent_team(game["teams"])
    selected = _selected_angle(packet)

    return (
        f"Washington Mystics postgame recap: the Mystics and {opponent['name']} finished at "
        f"{narrative.get('final_score')}, with the story centered on "
        f"{selected.get('angle_title', 'the main game angle').lower()}. "
        "This WNBA recap focuses on final score context, quarter scoring, turnovers, rebounds, bench production, "
        "and top performers from Washington's matchup."
    )


def render_social_caption_asset(packet: dict[str, Any]) -> str:
    """Render a concise Instagram/X-compatible caption with the final score."""
    final_score = packet["narrative"].get("final_score", "Final score unavailable")
    phrase = _asset_angle_phrase(packet, compact=False)
    return f"Final: {final_score}. {phrase} #Mystics #WNBA"


def generate_headline_candidates(packet: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate exactly five headline candidates ranked best to worst."""
    game = packet["game"]
    narrative = packet["narrative"]
    opponent = _opponent_team(game["teams"])
    opponent_short = opponent["name"].replace("Washington ", "")
    selected = _selected_angle(packet)
    base_confidence = float(selected.get("confidence") or 0.55)
    best_mystic = _best_mystics_performer(packet)
    result = narrative.get("result")
    loss = result != "win"

    if loss:
        rows = [
            (_headline(packet), "direct postgame analysis", base_confidence + 0.03),
            (f"Mystics' possession math catches up in loss to {opponent_short}", "clear explanatory", base_confidence),
            (f"Mystics fall to {opponent_short} as key quarter widens gap", "scoreboard-driven", base_confidence - 0.04),
            (f"{best_mystic.get('player', 'Washington leader')}'s line gives Mystics a starting point in loss", "player entry point", base_confidence - 0.08),
            (f"What the box score says about Mystics-{opponent_short}", "analytical", base_confidence - 0.12),
        ]
    else:
        rows = [
            (_headline(packet), "direct postgame analysis", base_confidence + 0.03),
            (f"Mystics use possession edge to finish off {opponent_short}", "clear explanatory", base_confidence),
            (f"Mystics beat {opponent_short} as key stretch holds up", "scoreboard-driven", base_confidence - 0.04),
            (f"{best_mystic.get('player', 'Washington leader')}'s line gives Mystics a postgame entry point", "player entry point", base_confidence - 0.08),
            (f"What the box score says about Mystics-{opponent_short}", "analytical", base_confidence - 0.12),
        ]

    return [
        {
            "rank": index,
            "headline": headline,
            "tone": tone,
            "confidence": _confidence(confidence),
            "risk_flags": _headline_risk_flags(packet, headline),
        }
        for index, (headline, tone, confidence) in enumerate(rows, start=1)
    ]


def write_editorial_assets(
    packet: dict[str, Any],
    *,
    asset_dir: Path = DEFAULT_ASSET_DIR,
    generated_at: str | None = None,
    assets: dict[str, Any] | None = None,
) -> tuple[dict[str, Path], Path]:
    """Write all secondary editorial assets and an index JSON file."""
    asset_dir.mkdir(parents=True, exist_ok=True)
    assets = assets or generate_editorial_assets(packet)
    event_id = packet["game"]["id"]
    file_contents = {
        "short_recap": (f"mystics-short-recap-{event_id}.md", f"# Short Recap\n\n{assets['short_recap']}\n"),
        "takeaways": (f"mystics-takeaways-{event_id}.md", _takeaways_markdown(assets["takeaways"])),
        "push_alert": (f"mystics-push-alert-{event_id}.txt", f"{assets['push_alert']}\n"),
        "newsletter_blurb": (
            f"mystics-newsletter-blurb-{event_id}.md",
            f"# Newsletter Blurb\n\n{assets['newsletter_blurb']}\n",
        ),
        "seo_summary": (f"mystics-seo-summary-{event_id}.md", f"# SEO Summary\n\n{assets['seo_summary']}\n"),
        "social_caption": (f"mystics-social-{event_id}.txt", f"{assets['social_caption']}\n"),
        "headline_candidates": (
            f"mystics-headlines-{event_id}.json",
            json.dumps(assets["headline_candidates"], indent=2, sort_keys=True) + "\n",
        ),
    }

    asset_paths: dict[str, Path] = {}
    for asset_key, (filename, content) in file_contents.items():
        path = asset_dir / filename
        path.write_text(content)
        asset_paths[asset_key] = path

    index_path = asset_dir / f"mystics-assets-index-{event_id}.json"
    index = format_asset_index(packet, asset_paths=asset_paths, generated_at=generated_at)
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    return asset_paths, index_path


def format_asset_index(
    packet: dict[str, Any],
    *,
    asset_paths: dict[str, Path | str],
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the review index for generated editorial assets."""
    selected = _selected_angle(packet)
    risk_flags = _asset_risk_flags(packet)
    writer = packet.get("writer_profile") or {}
    index = {
        "event_id": packet["game"]["id"],
        "generation_timestamp": generated_at or iso_utc(),
        "generated_asset_paths": {key: _display_path(path) for key, path in sorted(asset_paths.items())},
        "selected_story_angle": selected,
        "writer": {
            "name": writer.get("name", "Maya Brooks"),
            "voice": writer.get("voice", MAYA_BROOKS_PROFILE["voice"]),
        },
        "risk_summary": {
            "summary": _risk_summary(risk_flags),
            "flags": risk_flags,
            "editorial_rules": _editorial_rules(packet),
        },
        "review_required": True,
    }
    return validate_asset_index(index)


def _validate_editorial_assets(assets: dict[str, Any]) -> None:
    short_words = _word_count(assets.get("short_recap", ""))
    if not 120 <= short_words <= 180:
        raise ValueError(f"Short recap asset is {short_words} words; expected 120-180")

    takeaways = assets.get("takeaways")
    if not isinstance(takeaways, list) or len(takeaways) != 3:
        raise ValueError("Takeaway asset must include exactly three bullets")
    for item in takeaways:
        if not isinstance(item, dict) or not item.get("title") or not item.get("explanation"):
            raise ValueError("Each takeaway must include a title and explanation")

    push = str(assets.get("push_alert") or "")
    if len(push) > 160:
        raise ValueError(f"Push alert asset is {len(push)} characters; expected <= 160")

    newsletter_words = _word_count(assets.get("newsletter_blurb", ""))
    if not 75 <= newsletter_words <= 120:
        raise ValueError(f"Newsletter blurb asset is {newsletter_words} words; expected 75-120")

    seo = str(assets.get("seo_summary") or "").strip()
    if not seo or "\n" in seo:
        raise ValueError("SEO summary asset must be one non-empty paragraph")

    headlines = assets.get("headline_candidates")
    if not isinstance(headlines, list) or len(headlines) != 5:
        raise ValueError("Headline candidate asset must include exactly five headlines")


def _best_mystics_performer(packet: dict[str, Any]) -> dict[str, Any]:
    for performer in (packet.get("narrative") or {}).get("top_performers") or []:
        if performer.get("team") == TEAM_NAME:
            return performer
    return {}


def _team_score_text(mystics: dict[str, Any], opponent: dict[str, Any]) -> str:
    if mystics.get("winner"):
        return f"{mystics['score']}-{opponent['score']}"
    return f"{opponent['score']}-{mystics['score']}"


def _asset_angle_phrase(packet: dict[str, Any], *, compact: bool) -> str:
    selected_title = (_selected_angle(packet).get("angle_title") or "").lower()
    result = (packet.get("narrative") or {}).get("result")
    outcome = "win" if result == "win" else "loss"
    if "possession" in selected_title:
        return f"Possession gaps shaped Washington's {outcome}." if compact else f"Possession gaps shaped Washington's {outcome}."
    if "run" in selected_title or "quarter" in selected_title:
        return f"A key run and quarter split shaped Washington's {outcome}." if compact else f"A key run and quarter split kept Washington chasing the scoreboard."
    best = _best_mystics_performer(packet).get("player") or "Washington's top performer"
    return f"{best}'s line framed Washington's {outcome}." if compact else f"{best}'s line gave Washington a clear entry point."


def _headline_risk_flags(packet: dict[str, Any], headline: str) -> list[str]:
    flags = _asset_risk_flags(packet)
    lower = headline.lower()
    play_by_play = ((packet.get("game") or {}).get("play_by_play") or {})
    if ("run" in lower or "stretch" in lower) and not play_by_play.get("available"):
        flags.append("Run or stretch language requires play-by-play support; use quarter totals if unavailable.")
    if any(marker in lower for marker in ("best", "worst", "first", "record", "season high", "career high")):
        flags.append("Avoid milestone language unless the available game data explicitly supports it.")
    return _dedupe_strings(flags)


def _takeaways_markdown(takeaways: list[dict[str, str]]) -> str:
    lines = ["# 3 Takeaways", ""]
    for item in takeaways:
        lines.append(f"- **{item['title']}:** {item['explanation']}")
    return "\n".join(lines) + "\n"


def _asset_risk_flags(packet: dict[str, Any]) -> list[str]:
    selected = _selected_angle(packet)
    flags = list(selected.get("risk_flags") or [])
    if not _editorial_rules(packet):
        flags.append("Editorial rules unavailable; editor should verify guardrails manually.")
    return _dedupe_strings(flags)


def _preview_asset_paths(packet: dict[str, Any], asset_dir: Path) -> dict[str, Path]:
    event_id = packet["game"]["id"]
    return {
        "headline_candidates": asset_dir / f"mystics-headlines-{event_id}.json",
        "newsletter_blurb": asset_dir / f"mystics-newsletter-blurb-{event_id}.md",
        "push_alert": asset_dir / f"mystics-push-alert-{event_id}.txt",
        "seo_summary": asset_dir / f"mystics-seo-summary-{event_id}.md",
        "short_recap": asset_dir / f"mystics-short-recap-{event_id}.md",
        "social_caption": asset_dir / f"mystics-social-{event_id}.txt",
        "takeaways": asset_dir / f"mystics-takeaways-{event_id}.md",
    }
