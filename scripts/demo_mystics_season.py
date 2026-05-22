#!/usr/bin/env python3
"""Demo: generate season-level Mystics articles with Opus 4.7 + accuracy pass + Discord push.

Two articles:
  1. "Are the Mystics Telling Us Who They Are?" — season analytical (covers all played games)
  2. Kiki Iriafen feature — uses her aggregated stats across games

Each article gets a separate fact-check pass against the raw season packet.

Requires env vars:
  ANTHROPIC_API_KEY     — for Opus 4.7 calls
  DISCORD_PROXY_URL     — CF Worker URL (optional; skips Discord if absent)
  DISCORD_PROXY_SECRET  — auth header (required if posting to Discord)

CLI:
  python scripts/demo_mystics_season.py                # post to Discord + save drafts
  python scripts/demo_mystics_season.py --no-discord   # save drafts only
  python scripts/demo_mystics_season.py --target MYSTICS  # override channel target
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# Make the project root importable when running as a script
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _load_dotenv() -> None:
    """Best-effort .env loader. Doesn't override already-set env vars."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

from ingestion.season_aggregator import fetch_season  # noqa: E402

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
DISCORD_PROXY_URL = os.environ.get("DISCORD_PROXY_URL")
DISCORD_PROXY_SECRET = os.environ.get("DISCORD_PROXY_SECRET")

MODEL = "claude-opus-4-7"
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
ADMIN_REVIEW_URL = "https://admin.thensmt.com/#/blogs"
NSMT_BLUE = 0x0E80FC

TEAM_NAME = "Washington Mystics"
TEAM_SLUG = "mystics"
TEAM_ID = "16"
LEAGUE = "WNBA"
PERSONA_NAME = "Sibyl Avery"
PERSONA_VOICE = "Insightful. Draws lines between possessions and player tendencies. Writes for serious WNBA fans in DC/MD/VA who want pattern recognition, not box-score recitation."


def load_kb() -> dict:
    path = PROJECT_ROOT / "data" / "teams" / f"{TEAM_SLUG}.json"
    return json.loads(path.read_text())


def _flatten(value: object) -> str:
    """Coerce dict/list/scalar KB fields into a short string the LLM can use."""
    if isinstance(value, dict):
        parts = [f"{k}: {v}" for k, v in value.items() if v not in (None, "")]
        return "; ".join(parts)
    if isinstance(value, list):
        return ", ".join(_flatten(v) for v in value if v)
    return str(value) if value is not None else ""


def format_kb_block(kb: dict) -> str:
    """Compact KB summary — only the timeless fields the writer needs."""
    lines = [f"Team KB ({TEAM_NAME}):"]
    if kb.get("current_record"):
        lines.append(f"- KB-listed record (may be stale): {kb['current_record']}")
    if kb.get("conference"):
        lines.append(f"- Conference: {kb['conference']}")
    if kb.get("head_coach"):
        lines.append(f"- Head coach: {_flatten(kb['head_coach'])}")
    if kb.get("venue"):
        lines.append(f"- Home venue: {_flatten(kb['venue'])}")
    if kb.get("roster"):
        lines.append("- Listed roster:")
        for p in kb["roster"]:
            name = p.get("name", "")
            pos = p.get("position", "")
            number = p.get("number", "")
            notes = p.get("notes", "")
            tag = f" ({pos}, #{number})" if pos else (f" (#{number})" if number else "")
            extra = f" — {notes}" if notes else ""
            lines.append(f"  · {name}{tag}{extra}")
    return "\n".join(lines)


def format_season_block(season: dict) -> str:
    """Render season aggregator output into a compact prompt block."""
    t = season.get("team_trends", {})
    lines = [
        f"Season packet ({TEAM_NAME}, {season.get('league', LEAGUE)} {season.get('season_year', '?')}):",
        f"- Record: {season['record']} (home {t.get('home_wl', '?')}, away {t.get('away_wl', '?')})",
        f"- PPG offense: {t.get('ppg_offense', 0)} | defense: {t.get('ppg_defense', 0)} | margin: {t.get('scoring_margin', 0)}",
        "",
        f"Played games ({len(season['played_games'])}, oldest first):",
    ]
    for g in season["played_games"]:
        lines.append(
            f"  {g['date']} {g['home_away']:5s} {g['result']:14s} vs {g['opponent']:25s} "
            f"@ {g['venue']:30s} att={g['attendance'] or '?'}"
        )
        if g.get("linescore"):
            lines.append(f"      linescore: {g['linescore']}")
        for beat in g.get("narrative_beats") or []:
            lines.append(f"      beat: {beat}")
        if g.get("win_prob_arc"):
            lines.append(f"      win_prob: {g['win_prob_arc']}")
        for row in (g.get("boxscore") or [])[:5]:
            lines.append(
                f"      box: {row['player']:25s} "
                f"{row['pts']:3d} pts, {row['reb']:2d} reb, {row['ast']:2d} ast, "
                f"{row['fg']} FG, {row['min']} min, {row['plus_minus']:+d}"
            )
    lines.append("")
    lines.append("Player season aggregates (sorted by composite):")
    for p in season["player_aggregates"][:8]:
        bg = p["best_game"]
        lines.append(
            f"  {p['player']:25s} G={p['games']} "
            f"{p['ppg']:5.1f}/{p['rpg']:4.1f}/{p['apg']:4.1f}  "
            f"best: {bg['stat_line']} on {bg['date']} ({bg['result']})"
        )
    lines.append("")
    lines.append("Upcoming games (next 5):")
    for g in season.get("upcoming_games", []):
        lines.append(f"  {g['date']} {g['home_away']:5s} vs {g['opponent']:25s} @ {g['venue']}")
    if season.get("confidence_notes"):
        lines.append("")
        lines.append("Confidence notes:")
        for n in season["confidence_notes"]:
            lines.append(f"  - {n}")
    return "\n".join(lines)


def opus_call(prompt: str, max_tokens: int = 4096, temperature: float = 0.7) -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set in env")
    resp = requests.post(
        ANTHROPIC_API,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def write_season_article(kb_block: str, season_block: str) -> str:
    prompt = f"""You are {PERSONA_NAME}, a beat-style sports writer for NSMT (Nova Sports Media Team), an independent media outlet covering DC/MD/VA sports.
Your byline is AI-authored — readers know that — but inside the article you write as the persona, not as an AI assistant.
Your voice: {PERSONA_VOICE}

{kb_block}

{season_block}

Write an analytical season-narrative article titled:

  "Are the Mystics Telling Us Who They Are?"

Length: 650-850 words.

Hard requirements:
- Use ONLY facts from the season packet above. If a number isn't in the packet, don't invent one.
- The KB's "current_record" may be stale; trust the season packet's record over the KB.
- Centerpiece angle: synthesize the entire season so far (6 games), not just the most recent game. The Dallas blowout (5/19) is ONE data point, not the centerpiece.
- The home 0-2 / away 3-1 split is a real and unusual pattern — engage with it.
- Forward-looking close: mention upcoming opponents from the packet (don't invent dates or opponents).
- DO write as a serious analyst: focus on patterns, tendencies, and what the games are revealing about this roster.
- DO NOT write as a generic recap. DO NOT lead with "the Mystics played" or "yesterday."
- DO NOT use bullet points or headers. Flowing paragraphs only.
- DO NOT use phrases like "stat sheet" or "across the board."
- DO NOT speculate about player feelings, locker room mood, or anything not present in the data.

End the article with a single-line excerpt for previews, prefixed `EXCERPT:` (max 160 chars).
"""
    return opus_call(prompt, max_tokens=4096, temperature=0.7).strip()


def write_iriafen_feature(kb_block: str, season_block: str) -> str:
    prompt = f"""You are {PERSONA_NAME}, writing for NSMT.
Your voice: {PERSONA_VOICE}

{kb_block}

{season_block}

Write a player feature titled with your own headline (one line, sentence case, no clickbait) about Kiki Iriafen, the Mystics forward. Length: 450-600 words.

Hard requirements:
- Use ONLY facts from the season packet above for any stat claim. If a number isn't there, don't invent one.
- The packet contains her per-game lines AND her season aggregates. Use both.
- Center the piece on what her early-season production says about her role on this team.
- Reference her best game directly (date, opponent, line) from the data.
- Connect her performance to team-level outcomes where the data supports it (e.g., her output in wins vs losses, or in road games vs home games — only if the data shows a real pattern).
- Avoid "stat sheet" / "across the board" / generic praise language.
- DO NOT use bullet points or headers. Flowing paragraphs only.
- DO NOT speculate about feelings, fit, or chemistry beyond what plays/stats support.

End with a single-line excerpt for previews, prefixed `EXCERPT:` (max 160 chars).
Put your headline as the first line of the article, prefixed `TITLE:`.
"""
    return opus_call(prompt, max_tokens=4096, temperature=0.7).strip()


def fact_check_article(article: str, season_packet_json: str) -> str:
    prompt = f"""You are a meticulous fact-checker. You are paid to find errors, not approve articles.

Below is the raw structured data the writer was given. Below that is the article they wrote.

Your job: extract every factual claim in the article (records, scores, stat lines, dates, opponents, venues, player names, runs, win-probability claims, ranking claims, attendance). For each claim, mark it:

  ✅ SUPPORTED — exactly matches the source data
  ⚠️ AMBIGUOUS — partly supported but slightly off (wrong rounding, opponent abbreviation, etc.)
  ❌ UNSUPPORTED — appears nowhere in source data, or directly contradicts it

Source data (JSON):
```
{season_packet_json}
```

Article:
```
{article}
```

Output format (strict):

VERDICT: PASS | NEEDS_REVISION | FAIL

CLAIMS:
1. "[exact quote from article]" → ✅/⚠️/❌  [one-sentence reason; cite source-data field name]
2. ...

NUMERIC FACT-CHECK (table of any numbers that appear in the article):
- claim_value  →  source_value  →  ✅/❌

SUMMARY: [2-3 sentences naming the most serious issues, or "no significant issues found"]

Do not invent issues. Do not be lenient. If the article mentions a player by name, the source data MUST list that player.
"""
    return opus_call(prompt, max_tokens=4096, temperature=0.0).strip()


def split_title_body_excerpt(text: str, default_title: str) -> tuple[str, str, str]:
    """Extract TITLE:, EXCERPT:, and body from the model's output."""
    lines = text.splitlines()
    title = default_title
    excerpt = ""
    body_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("TITLE:"):
            title = stripped.split(":", 1)[1].strip().strip('"\'')
            continue
        if stripped.upper().startswith("EXCERPT:"):
            excerpt = stripped.split(":", 1)[1].strip()
            continue
        body_lines.append(line)
    body = "\n".join(body_lines).strip()
    return title, body, excerpt


def post_to_discord(
    *,
    title: str,
    body: str,
    excerpt: str,
    fact_check: str,
    target: str,
) -> bool:
    if not DISCORD_PROXY_URL or not DISCORD_PROXY_SECRET:
        print(f"  [discord:{target}] skipped — env vars not set")
        return False

    verdict_line = next(
        (ln for ln in fact_check.splitlines() if ln.strip().upper().startswith("VERDICT:")),
        "VERDICT: (verdict line missing)",
    )

    MAX_DESC = 3800
    body_text = (body or "").strip() or "(no body provided)"
    if len(body_text) > MAX_DESC:
        body_text = body_text[:MAX_DESC].rstrip() + "…\n\n[Continue reading in admin →](" + ADMIN_REVIEW_URL + ")"

    embed = {
        "title": f"🟢 DEMO — {title}",
        "description": body_text,
        "color": NSMT_BLUE,
        "fields": [
            {"name": "✍️ Byline", "value": f"{PERSONA_NAME} (AI · NSMT)", "inline": False},
            {"name": "🧾 Excerpt", "value": excerpt or "(none)", "inline": False},
            {"name": "🔍 Fact-check", "value": verdict_line.strip(), "inline": False},
            {"name": "🤖 Model", "value": MODEL, "inline": True},
        ],
        "footer": {"text": "Demo run · NSMT content pipeline"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    payload = {
        "thread_name": f"DEMO — {title}"[:99],
        "embeds": [embed],
    }
    resp = requests.post(
        DISCORD_PROXY_URL,
        headers={
            "X-NSMT-Auth": DISCORD_PROXY_SECRET,
            "X-NSMT-Target": target,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=20,
    )
    if resp.status_code < 300:
        print(f"  [discord:{target}] ✓ posted")
        return True
    print(f"  [discord:{target}] ✗ status {resp.status_code}: {resp.text[:200]}")
    return False


def post_fact_check_to_discord(*, title: str, fact_check: str, target: str) -> bool:
    """Post the full fact-check report as a follow-up message in the same channel."""
    if not DISCORD_PROXY_URL or not DISCORD_PROXY_SECRET:
        return False

    MAX_DESC = 3800
    text = fact_check.strip()
    if len(text) > MAX_DESC:
        text = text[:MAX_DESC].rstrip() + "…"

    embed = {
        "title": f"🔍 Fact-check — {title}",
        "description": f"```\n{text}\n```"[:MAX_DESC],
        "color": 0x999999,
        "footer": {"text": "Opus 4.7 adversarial pass against raw season packet"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    payload = {"embeds": [embed]}
    resp = requests.post(
        DISCORD_PROXY_URL,
        headers={
            "X-NSMT-Auth": DISCORD_PROXY_SECRET,
            "X-NSMT-Target": target,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=20,
    )
    return resp.status_code < 300


def save_local(title: str, body: str, excerpt: str, fact_check: str, slug: str) -> Path:
    drafts = PROJECT_ROOT / "drafts"
    drafts.mkdir(exist_ok=True)
    path = drafts / f"demo-{datetime.now().strftime('%Y%m%d')}-{slug}.md"
    path.write_text(
        f"# {title}\n\n"
        f"**Persona:** {PERSONA_NAME}  \n"
        f"**Model:** {MODEL}  \n"
        f"**Excerpt:** {excerpt}\n\n"
        f"---\n\n"
        f"{body}\n\n"
        f"---\n\n"
        f"## Fact-check\n\n"
        f"```\n{fact_check}\n```\n"
    )
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-discord", action="store_true", help="Skip Discord push, save markdown only.")
    ap.add_argument("--target", default="RECAPS", help="Discord channel target on the CF Worker (default RECAPS).")
    args = ap.parse_args()

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set. export ANTHROPIC_API_KEY=... and re-run.", file=sys.stderr)
        return 2

    print(f"[demo] Fetching Mystics season from ESPN (team_id={TEAM_ID})...")
    season = fetch_season(TEAM_ID, TEAM_NAME, sport="basketball", league_slug="wnba")
    print(f"[demo] Pulled {len(season['played_games'])} games. Record: {season['record']}")

    kb = load_kb()
    kb_block = format_kb_block(kb)
    season_block = format_season_block(season)
    season_json = json.dumps(season, indent=2, default=str)

    target = args.target
    post_discord = not args.no_discord

    print("\n[demo] Article 1: season analytical — generating...")
    article_1 = write_season_article(kb_block, season_block)
    title_1, body_1, excerpt_1 = split_title_body_excerpt(article_1, "Are the Mystics Telling Us Who They Are?")
    title_1 = "Are the Mystics Telling Us Who They Are?"
    print(f"[demo] Article 1 draft: {len(body_1)} chars. Fact-checking...")
    fact_1 = fact_check_article(body_1, season_json)
    saved_1 = save_local(title_1, body_1, excerpt_1, fact_1, "mystics-season-analytical")
    print(f"[demo] Article 1 saved: {saved_1.relative_to(PROJECT_ROOT)}")

    print("\n[demo] Article 2: Iriafen feature — generating...")
    article_2 = write_iriafen_feature(kb_block, season_block)
    title_2, body_2, excerpt_2 = split_title_body_excerpt(article_2, "Kiki Iriafen Has Been the Mystics' Most Consistent Force")
    print(f"[demo] Article 2 draft: {len(body_2)} chars. Fact-checking...")
    fact_2 = fact_check_article(body_2, season_json)
    saved_2 = save_local(title_2, body_2, excerpt_2, fact_2, "mystics-iriafen-feature")
    print(f"[demo] Article 2 saved: {saved_2.relative_to(PROJECT_ROOT)}")

    if post_discord:
        print(f"\n[demo] Posting to Discord (target={target})...")
        post_to_discord(title=title_1, body=body_1, excerpt=excerpt_1, fact_check=fact_1, target=target)
        post_fact_check_to_discord(title=title_1, fact_check=fact_1, target=target)
        post_to_discord(title=title_2, body=body_2, excerpt=excerpt_2, fact_check=fact_2, target=target)
        post_fact_check_to_discord(title=title_2, fact_check=fact_2, target=target)
    else:
        print("\n[demo] --no-discord set; skipped Discord push.")

    print("\n[demo] Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
