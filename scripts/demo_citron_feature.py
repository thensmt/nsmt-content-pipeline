#!/usr/bin/env python3
"""One-off demo: Sonia Citron player feature using the new generate_content.py
helpers (KB context with tenure, GUARDRAILS, in-line Sonnet fact-check pass,
Discord post via the CF Worker proxy).

This is a player feature, not a game recap, so we bypass the main run() loop
and call the helpers directly with a Citron-specific prompt. Everything else
— writer model, KB block, fact-check pass, Discord embed format — flows
through the same code path the daily cron uses, so this is a true end-to-end
test of the tightened pipeline architecture.

CLI:
  python scripts/demo_citron_feature.py                       # write + fact-check + post to Discord
  python scripts/demo_citron_feature.py --no-discord          # write + fact-check, print only
  python scripts/demo_citron_feature.py --no-fact-check       # skip the in-line fact-check pass

Reuses env loading + the Discord proxy already wired up in generate_content.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _load_env() -> None:
    """Best-effort .env loader — runs BEFORE importing generate_content so
    its module-level os.environ.get() calls see the values. In GH Actions
    env vars are set via the workflow `env:` block before Python starts,
    so this is a no-op there."""
    for env_path in [
        PROJECT_ROOT / ".env",
        Path.home() / "Downloads/Claude/nsmt-discord/.env",
    ]:
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


_load_env()

from generate_content import (  # noqa: E402
    ALL_TEAMS,
    ADMIN_REVIEW_URL,
    ANTHROPIC_API_KEY,
    DISCORD_PROXY_URL,
    DISCORD_PROXY_SECRET,
    GUARDRAILS,
    NSMT_BLUE,
    build_byline,
    fact_check_article,
    kb_context_block,
    load_story_packet,
    load_team_kb,
)
from generate_content import _VERDICT_BADGES, _VERDICT_COLORS  # noqa: E402

TEAM_NAME = "Washington Mystics"


def get_mystics() -> dict:
    for t in ALL_TEAMS:
        if t["name"] == TEAM_NAME:
            return t
    raise RuntimeError(f"{TEAM_NAME} not found in ALL_TEAMS")


def call_sonnet(prompt: str, max_tokens: int = 1500) -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()


def write_citron_feature(team: dict, kb: dict | None, packet: dict | None) -> str:
    persona_name = team.get("persona") or "an NSMT writer"
    persona_voice = team.get("voice") or "professional and engaging"
    kb_block = kb_context_block(kb) if kb else ""
    # Compact packet rendering — full block is overkill for a player feature.
    packet_block = ""
    if packet:
        packet_block = "\n\nStory packet (timely game data):\n" + json.dumps(packet, indent=2, default=str)[:6000]

    prompt = f"""You are {persona_name}, an AI sports writer for NSMT (Nova Sports Media Team), the DMV's premier independent sports media outlet covering Washington DC, Maryland, and Virginia. NSMT is transparent that you are an AI — readers know your byline is AI-authored. Your voice: {persona_voice}.
{kb_block}{packet_block}

Write a focused player feature (550-750 words) on Sonia Citron, the Washington Mystics guard.

Article angle: what Sonia Citron's early-season production tells us about her role on this team — and what it doesn't. She is one of the team's leading scorers; lean into her efficiency patterns (shooting splits across games, her best individual performance, when her scoring correlates with team outcomes).

Hard requirements:
- Use ONLY facts from the Verified team context and the Story packet (if present) above. The Verified roster lists every Mystics player you may reference. If a stat, date, opponent, score, venue, or biographical detail isn't in those blocks, do not invent one.
- The Verified roster shows Sonia Citron as G #22 with no tenure notes — DO NOT call her a rookie, first-year, second-year, or refer to her draft year/pick/college unless the source explicitly provides that information.
- Quote per-game stats and shooting splits directly from the packet's boxscore for the game in question; do not paraphrase or compute deltas in your head.
- Connect her performances to team outcomes only when the source data supports it (e.g., her line in wins vs losses, or in road games vs home games — only if the data shows a real pattern).
- Stay in your persona voice but keep it professional, written for DC/MD/VA sports fans.
- Do NOT refer to yourself in first person or call attention to being an AI in the body — the byline handles disclosure.
- Format: plain paragraphs only, no headers, no bullet points.

Editorial guardrails (HARD requirements):
{GUARDRAILS}

Output your headline as the very first line, prefixed `TITLE:` (sentence case, no clickbait, one line).
End with a single-line preview teaser prefixed `EXCERPT:` (max 160 characters).
"""
    return call_sonnet(prompt, max_tokens=2048)


def split_title_body_excerpt(text: str, default_title: str) -> tuple[str, str, str]:
    title, excerpt = default_title, ""
    body_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("TITLE:"):
            title = stripped.split(":", 1)[1].strip().strip('"\'') or default_title
            continue
        if stripped.upper().startswith("EXCERPT:"):
            excerpt = stripped.split(":", 1)[1].strip()
            continue
        body_lines.append(line)
    body = "\n".join(body_lines).strip()
    return title, body, excerpt


def post_feature_to_discord(team: dict, title: str, body: str, excerpt: str,
                            verdict: str, report: str | None) -> bool:
    if not DISCORD_PROXY_URL or not DISCORD_PROXY_SECRET:
        print("  Discord post skipped — DISCORD_PROXY_URL / DISCORD_PROXY_SECRET not set.")
        return False
    MAX = 3900
    body_text = (body or "").strip() or "(no body provided)"
    if len(body_text) > MAX:
        body_text = body_text[:MAX].rstrip() + "…\n\n[Continue reading in admin →](" + ADMIN_REVIEW_URL + ")"
    byline = build_byline(team)
    badge = _VERDICT_BADGES.get(verdict, _VERDICT_BADGES["UNKNOWN"])
    color = _VERDICT_COLORS.get(verdict, NSMT_BLUE)
    embed = {
        "title":       f"🎯 Player Feature — {title}",
        "description": body_text,
        "color":       color,
        "fields": [
            {"name": "✍️ Byline",     "value": byline,                            "inline": False},
            {"name": "🏆 Team",       "value": team["name"],                      "inline": True},
            {"name": "🔍 Fact-check", "value": badge,                             "inline": True},
            {"name": "🤖 Model",      "value": "claude-sonnet-4-6",               "inline": True},
            {"name": "🧾 Excerpt",    "value": excerpt or "(none)",               "inline": False},
        ],
        "footer":    {"text": f"{team['league']} · one-off Citron feature demo · Codex second-opinion will reply"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    thread_name = f"Player Feature — Sonia Citron — {date.today().isoformat()}"[:99]
    payload = {"thread_name": thread_name, "embeds": [embed]}
    resp = requests.post(
        DISCORD_PROXY_URL,
        headers={
            "X-NSMT-Auth":   DISCORD_PROXY_SECRET,
            "X-NSMT-Target": team.get("channel_target") or "RECAPS",
            "Content-Type":  "application/json",
        },
        json=payload,
        timeout=15,
    )
    if resp.status_code >= 300:
        print(f"  ✗ Discord post failed (status {resp.status_code}): {resp.text[:200]}")
        return False
    print(f"  ✓ Discord post created (status {resp.status_code})")
    # Post fact-check follow-up when verdict != PASS, matching generate_content.py behavior
    if report and verdict in {"NEEDS_REVISION", "FAIL"}:
        text = report.strip()
        if len(text) > 3800:
            text = text[:3800].rstrip() + "…"
        followup = {
            "title":       f"🔍 In-line fact-check — {title[:160]} — {badge}",
            "description": f"```\n{text}\n```",
            "color":       color,
            "footer":      {"text": "claude-sonnet-4-6 adversarial pass · independent of codex_review.py"},
            "timestamp":   datetime.now(timezone.utc).isoformat(),
        }
        r2 = requests.post(
            DISCORD_PROXY_URL,
            headers={
                "X-NSMT-Auth":   DISCORD_PROXY_SECRET,
                "X-NSMT-Target": team.get("channel_target") or "RECAPS",
                "Content-Type":  "application/json",
            },
            json={"embeds": [followup]},
            timeout=15,
        )
        if r2.status_code >= 300:
            print(f"  ✗ Fact-check follow-up failed (status {r2.status_code}): {r2.text[:200]}")
        else:
            print(f"  ✓ Fact-check follow-up posted (status {r2.status_code})")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-discord", action="store_true")
    ap.add_argument("--no-fact-check", action="store_true")
    args = ap.parse_args()

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        return 2

    team = get_mystics()
    today = date.today()
    print(f"[demo] target team: {team['name']} ({team['persona']}), date: {today}")

    kb = load_team_kb(team)
    packet = load_story_packet(team, today)
    print(f"[demo] KB loaded: {bool(kb)}  ·  story packet loaded: {bool(packet)}")

    print("[demo] writing Citron feature via Sonnet 4.6…")
    raw = write_citron_feature(team, kb, packet)
    title, body, excerpt = split_title_body_excerpt(raw, "Sonia Citron Has Been Mystics' Most Reliable Scoring Engine")
    print(f"[demo] draft: {len(body)} chars, title: {title!r}")

    verdict, report = "UNKNOWN", None
    if not args.no_fact_check:
        print("[demo] running in-line Sonnet fact-check pass…")
        verdict, report = fact_check_article(body, kb, packet, team)
        print(f"[demo] fact-check verdict: {verdict}")

    drafts = PROJECT_ROOT / "drafts"
    drafts.mkdir(exist_ok=True)
    path = drafts / f"citron-feature-{today.isoformat()}.md"
    path.write_text(
        f"# {title}\n\n"
        f"**Persona:** {team['persona']}  \n"
        f"**Model:** claude-sonnet-4-6  \n"
        f"**Verdict:** {verdict}  \n"
        f"**Excerpt:** {excerpt}\n\n"
        f"---\n\n{body}\n\n"
        f"---\n\n## In-line fact-check\n\n```\n{report or '(none)'}\n```\n"
    )
    print(f"[demo] local draft saved: {path.relative_to(PROJECT_ROOT)}")

    if args.no_discord:
        print("[demo] --no-discord set, skipped Discord push.")
    else:
        print("[demo] posting to Discord (RECAPS target)…")
        post_feature_to_discord(team, title, body, excerpt, verdict, report)

    print("[demo] done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
