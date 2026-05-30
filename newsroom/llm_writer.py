"""LLM recap writer for the Mystics beat (Maya Brooks).

This module is the DELIBERATE point where the newsroom package gains an LLM
call. It writes a postgame recap that reads like a beat writer who watched the
game, grounding game facts in the normalized packet and drawing
narrative/atmosphere from the attached transcripts. The writer itself does not
touch the admin API, Discord, or Contentful — orchestration and review routing
stay in ingestion/mystics_postgame_recap.py.

API mechanics mirror generate_content.generate_article: a raw requests.post to
the Anthropic Messages API (no SDK), x-api-key from ANTHROPIC_API_KEY, the
web_search server tool (max_uses 2), and the shared GUARDRAILS / style blocks
from style_guide.py. Prompt caching (GA; no beta header) caches the static
prefix (guardrails + style + persona) and the media_transcripts block.

The HTTP call is injectable via ``transport`` so tests run fully offline.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from newsroom.claim_audit import verify_quotes
from newsroom.common import (
    TEAM_ABBR,
    TEAM_ID,
    TEAM_NAME,
    _display_date,
    _opponent_team,
    _selected_angle,
    _team_by_id,
)
from newsroom.memory import _external_memory_context_summary
from style_guide import (
    AI_TELLS_AVOIDANCE,
    GUARDRAILS,
    NO_META_COMMENTARY,
    SOURCE_HIERARCHY_RULE,
)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-6"
# web_search is OFF for the Mystics writer. The 2026-05-29 live run showed it
# inventing a coach ("Sindey Carter") and sourcing non-verbatim quotes; the
# packet + transcript already carry every fact this recap needs. The generic
# generate_content.py writer keeps its own web_search setting untouched.
MAX_WEB_SEARCHES = 0
MAX_TOKENS = 2048

# Standard published Sonnet rates ($/token). Cache write = 1.25x input, cache
# read = 0.1x input. Used only for the cost estimate in reporting; verify
# against current Anthropic pricing before trusting the dollar figure.
PRICING = {
    "claude-sonnet-4-6": {
        "input": 3.0 / 1_000_000,
        "output": 15.0 / 1_000_000,
        "cache_write": 3.75 / 1_000_000,
        "cache_read": 0.30 / 1_000_000,
    }
}


# ── House rules specific to the Mystics LLM recap ──────────────────────────────

_HOUSE_RULES = (
    "NSMT HOUSE RULES (hard):\n"
    "- No em dashes. Not one, anywhere. Use a comma, a period, or rephrase.\n"
    "- Straight quotes only. Never curly quotes.\n"
    "- Write like a human beat writer who watched the game, not like an AI "
    "summarizing a box score.\n"
    "- Keep AI disclosure in the byline, never in the article body."
)

_TRANSCRIPT_RULES = (
    "TRANSCRIPT USAGE RULES (hard safety boundary):\n"
    "- Any transcript below is AUTO-GENERATED captions (ASR) and may contain "
    "errors. Prefer the corrected text shown.\n"
    "- BROADCAST / HIGHLIGHTS commentary: use ONLY as narrative and atmosphere "
    "fuel, fully paraphrased in your own words. NEVER quote an announcer or "
    "broadcaster, and NEVER attribute anything to them.\n"
    "- PRESS CONFERENCE: you MAY use direct quotes, but ONLY text copied word "
    "for word from the corrected press-conference transcript below, wrapped in "
    "straight quotes. Only attribute a quote to a named person when the "
    "surrounding transcript context makes the speaker unambiguous. If you are "
    "not certain who said it, drop the quote or use it without naming a "
    "speaker.\n"
    "- NEVER invent a quote, NEVER paraphrase something into quotation marks, "
    "and NEVER put quotation marks around text that is not verbatim in the "
    "corrected press-conference transcript. Every quotation mark you write must "
    "wrap text that appears verbatim in that transcript. Fabricated or altered "
    "quotes are automatically rejected.\n"
    "- The attached press-conference transcript is the ONLY permitted source of "
    "any quotation. NEVER take a quote from web_search results or from memory. If "
    "you use web_search at all, use it only to confirm a non-quote fact, never to "
    "find or source a quote.\n"
    "- When you do quote, copy the span EXACTLY as it appears in the corrected "
    "press-conference text: same words, same order, no cleanup. Do not fix "
    "grammar, merge two sentences, or swap words. If no verbatim sentence is worth "
    "quoting, paraphrase the idea WITHOUT quotation marks instead."
)


def build_system_prefix(writer_profile: dict[str, Any]) -> str:
    """The static, cacheable prefix: persona + style + guardrails + transcript rules."""
    name = writer_profile.get("name") or "an NSMT beat writer"
    title = writer_profile.get("title") or "AI beat writer"
    publication = writer_profile.get("publication") or "NSMT"
    voice = writer_profile.get("voice") or "clear, observant, basketball-literate"
    focus = ", ".join(writer_profile.get("focus_areas") or []) or "team-level game flow"
    writer_guardrails = "\n".join(f"- {rule}" for rule in writer_profile.get("guardrails") or [])

    return (
        f"You are {name}, {publication} {title}. Your voice: {voice}.\n"
        f"Focus areas: {focus}.\n\n"
        "You are writing a WNBA postgame recap that reads like a beat writer who "
        "watched the game live, not a box-score summary.\n\n"
        f"{NO_META_COMMENTARY}\n\n"
        f"{AI_TELLS_AVOIDANCE}\n\n"
        f"{_HOUSE_RULES}\n\n"
        "EDITORIAL GUARDRAILS (hard requirements):\n"
        f"{GUARDRAILS}\n\n"
        f"{SOURCE_HIERARCHY_RULE}\n\n"
        "WRITER GUARDRAILS:\n"
        f"{writer_guardrails}\n\n"
        f"{_TRANSCRIPT_RULES}"
    )


def build_transcripts_block(packet: dict[str, Any]) -> str:
    """The cacheable transcript block (corrected ASR text, labeled by kind)."""
    transcripts = [
        t
        for t in (packet.get("media_transcripts") or [])
        if isinstance(t, dict) and t.get("status") == "ok"
    ]
    if not transcripts:
        return (
            "ATTACHED TRANSCRIPTS: none for this game. Write from the verified "
            "facts only and use no direct quotes."
        )

    sections = ["ATTACHED TRANSCRIPTS (auto-generated ASR; prefer corrected text; follow the usage rules):"]
    for index, t in enumerate(transcripts, start=1):
        corrected = (t.get("corrected_text") or t.get("text") or "").strip()
        kind = t.get("kind") or "video"
        track = t.get("track") or "auto"
        video_id = t.get("video_id") or ""
        if kind == "presser":
            header = (
                f"[{index}] PRESS CONFERENCE, video {video_id} ({track} captions). "
                "Direct quotes allowed ONLY verbatim from this corrected text:"
            )
        else:
            header = (
                f"[{index}] BROADCAST HIGHLIGHTS COMMENTARY, video {video_id} ({track} captions). "
                "Atmosphere and paraphrase ONLY. Do not quote or attribute:"
            )
        sections.append(f"{header}\n\"\"\"\n{corrected}\n\"\"\"")
    return "\n\n".join(sections)


def _performer_line(performer: dict[str, Any]) -> str:
    bits = [f"{performer.get('player', 'Unknown')} ({performer.get('team', '')})"]
    stat_line = performer.get("stat_line")
    if stat_line:
        bits.append(f": {stat_line}")
    extras = []
    if performer.get("fg"):
        extras.append(f"FG {performer['fg']}")
    if performer.get("three_pt"):
        extras.append(f"3PT {performer['three_pt']}")
    if extras:
        bits.append(f" ({'; '.join(extras)})")
    return "".join(bits)


def build_facts_block(packet: dict[str, Any]) -> str:
    """The dynamic per-game block: verified facts + memory + suggested angle + task."""
    game = packet["game"]
    narrative = packet["narrative"]
    opponent = _opponent_team(game["teams"])
    mystics = _team_by_id(game["teams"], TEAM_ID)
    edges = narrative.get("stat_edges") or {}

    quarter_line = ", ".join(
        f"{row['label']} {row.get(opponent['abbreviation'], row.get(opponent['name']))}"
        f"-{row.get(TEAM_ABBR, row.get(TEAM_NAME))}"
        for row in game.get("scoring_by_quarter", [])
    )
    performers = "\n".join(f"  - {_performer_line(p)}" for p in narrative.get("top_performers") or [])

    def edge(key: str) -> str:
        e = edges.get(key) or {}
        return f"Washington {e.get('mystics')} vs {opponent['name']} {e.get('opponent')}"

    schedule = packet.get("schedule") or {}
    next_event = schedule.get("next_event") or {}
    next_line = (
        f"{next_event.get('name')} on {_display_date(next_event.get('date'))}"
        if next_event.get("name")
        else "not listed"
    )

    memory = _external_memory_context_summary(packet)
    memory_lines = []
    for lens in memory.get("player_profile_lenses", [])[:6]:
        memory_lines.append(f"  - {lens.get('player')}: {lens.get('editorial_lens')}")
    for narr in memory.get("season_narratives", [])[:3]:
        memory_lines.append(f"  - Season framing ({narr.get('label')}): {narr.get('context')}")
    memory_text = "\n".join(memory_lines) or "  - (no editorial memory loaded)"

    selected = _selected_angle(packet)
    angle_text = (
        f"{selected.get('angle_title', '')}: {selected.get('angle_summary', '')}"
        if selected
        else "none"
    )

    return (
        "VERIFIED GAME FACTS (use these numbers verbatim; do not invent or recompute):\n"
        f"- Matchup: {game.get('name', '')}\n"
        f"- Date and venue: {_display_date(game.get('date'))}, {game.get('venue', 'the arena')}\n"
        f"- Final score: {narrative.get('final_score')} (Washington {narrative.get('result')})\n"
        f"- Washington {mystics.get('score')}, {opponent['name']} {opponent.get('score')}\n"
        f"- Score by quarter (opp-WSH): {quarter_line}\n"
        f"- Top performers:\n{performers}\n"
        f"- Biggest run: {(narrative.get('biggest_scoring_run') or {}).get('summary', '')}\n"
        f"- Turning point: {(narrative.get('key_quarter_or_turning_point') or {}).get('summary', '')}\n"
        f"- Rebounds: {edge('rebounds')}\n"
        f"- Turnovers: {edge('turnovers')}\n"
        f"- Bench points: {edge('bench_points')}\n"
        f"- Three-point makes: {edge('three_point_makes')}\n"
        f"- Points in paint: {edge('points_in_paint')}\n"
        f"- Next game: {next_line}\n\n"
        "EDITORIAL MEMORY (context only, never presented as current-game fact):\n"
        f"{memory_text}\n\n"
        f"SUGGESTED ANGLE (optional frame, not a requirement): {angle_text}\n\n"
        "TASK:\n"
        "Write the recap now, 600 to 750 words, in your voice. Lead with the moment "
        "or matchup that decided the game. Use the highlights only as atmosphere. "
        "Quote sparingly: use at most ONE or TWO direct quotes, and ONLY a single "
        "uninterrupted sentence you can reproduce word for word from the press-conference "
        "transcript with zero changes. Never split one spoken statement into multiple "
        "quoted fragments, and never trim filler from inside a quoted span. If a line "
        "needs any cleanup to read well, paraphrase it without quotation marks instead. "
        "When in doubt, paraphrase. Close on a concrete stat or a quote, not a cliche. "
        "Remember: no em dashes, straight quotes only, and every quoted span must be "
        "verbatim from the corrected press-conference transcript.\n\n"
        "Output EXACTLY this structure and nothing else:\n"
        "HEADLINE: <one line, no surrounding quotes>\n"
        "\n"
        "<article body as plain paragraphs, no markdown headers, no bullet lists>\n"
        "\n"
        "EXCERPT: <one sentence teaser, max 160 characters>"
    )


def _build_payload(packet: dict[str, Any], writer_profile: dict[str, Any]) -> dict[str, Any]:
    model = writer_profile.get("model") or DEFAULT_MODEL
    system_prefix = build_system_prefix(writer_profile)
    transcripts_block = build_transcripts_block(packet)
    facts_block = build_facts_block(packet)
    payload = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        # Cache breakpoint 1: the static persona + style + guardrails prefix.
        "system": [
            {"type": "text", "text": system_prefix, "cache_control": {"type": "ephemeral"}}
        ],
        "messages": [
            {
                "role": "user",
                "content": [
                    # Cache breakpoint 2: the transcript block, reused across the
                    # write call (and future calls on the same game).
                    {"type": "text", "text": transcripts_block, "cache_control": {"type": "ephemeral"}},
                    # Dynamic per-game facts + task (not cached).
                    {"type": "text", "text": facts_block},
                ],
            }
        ],
    }
    # web_search only when explicitly re-enabled (MAX_WEB_SEARCHES > 0). Omitting
    # the tool entirely (rather than passing max_uses 0) keeps the request valid.
    if MAX_WEB_SEARCHES > 0:
        payload["tools"] = [
            {"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_WEB_SEARCHES}
        ]
    return payload


def _default_transport(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    try:
        import requests
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("requests is required for the LLM writer") from exc
    response = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        json=payload,
        timeout=180,
    )
    response.raise_for_status()
    return response.json()


def _concat_text(response: dict[str, Any]) -> str:
    # web_search interleaves text + tool_use + tool_result blocks; keep text only.
    blocks = response.get("content") or []
    return "\n\n".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()


def _parse_output(text: str) -> tuple[str, str, str]:
    import re

    work = text.strip()
    excerpt = ""
    if "EXCERPT:" in work:
        work, _, tail = work.rpartition("EXCERPT:")
        excerpt = tail.strip().splitlines()[0].strip() if tail.strip() else ""
        work = work.strip()

    match = re.search(r"(?im)^\s*HEADLINE:\s*(.+?)\s*$", work)
    if match:
        headline = match.group(1).strip().strip('"').strip()
        body = work[match.end():].strip()
    else:
        lines = work.splitlines()
        headline = (lines[0].strip().lstrip("#").strip() if lines else "")
        body = "\n".join(lines[1:]).strip()

    # Drop any stray leading markdown header the model may have added to the body.
    body = re.sub(r"^\s*#+\s.*\n+", "", body).strip()
    return headline, body, excerpt


def _fallback_excerpt(body: str) -> str:
    import re

    first = re.split(r"(?<=[.!?])\s+", body.strip(), maxsplit=1)[0] if body.strip() else ""
    return first[:158]


def estimate_cost(usage: dict[str, Any], model: str = DEFAULT_MODEL) -> dict[str, float]:
    """Estimate USD cost from a Messages API usage dict using standard Sonnet rates."""
    rates = PRICING.get(model, PRICING[DEFAULT_MODEL])
    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    cache_write = int(usage.get("cache_creation_input_tokens") or 0)
    cache_read = int(usage.get("cache_read_input_tokens") or 0)
    cost = (
        inp * rates["input"]
        + out * rates["output"]
        + cache_write * rates["cache_write"]
        + cache_read * rates["cache_read"]
    )
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_creation_input_tokens": cache_write,
        "cache_read_input_tokens": cache_read,
        "estimated_usd": round(cost, 6),
        "rate_note": f"standard {model} rates: $3/$15 per MTok in/out, cache write 1.25x, cache read 0.1x",
    }


def write_recap(
    packet: dict[str, Any],
    *,
    writer_profile: dict[str, Any] | None = None,
    transport: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Generate an LLM recap for the Mystics packet.

    Returns {headline, body, excerpt, used_segments, model, usage, raw_text}.
    Raises RuntimeError on missing key / API failure so the caller can fall back
    to the deterministic render. Does not publish or write any files.
    """
    profile = writer_profile or packet.get("writer_profile") or {}
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    send = transport or _default_transport
    if transport is None and not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set; cannot run the LLM writer")

    payload = _build_payload(packet, profile)
    response = send(payload, key or "")
    raw_text = _concat_text(response)
    if not raw_text:
        raise RuntimeError("LLM writer returned no text content")

    headline, body, excerpt = _parse_output(raw_text)
    if not headline or not body:
        raise RuntimeError("LLM writer output missing headline or body")
    if not excerpt:
        excerpt = _fallback_excerpt(body)

    quote_check = verify_quotes(body, packet)
    return {
        "headline": headline,
        "body": body,
        "excerpt": excerpt,
        "used_segments": quote_check["used_segments"],
        "quote_verification": quote_check,
        "model": payload["model"],
        "usage": response.get("usage") or {},
        "raw_text": raw_text,
    }
