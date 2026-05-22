#!/usr/bin/env python3
"""Local-only: independent second-opinion review of NSMT recap-pipeline articles.

Polls Discord #recap-pipeline forum threads for new article posts, refetches
the *same source set the writer saw* (team KB + story packet), runs each
article through Codex CLI (your ChatGPT subscription auth — no OpenAI API
key), and posts a verdict embed as a reply inside the same forum thread.

Complementary to the in-line fact_check_article() pass in generate_content.py:
that pass uses Sonnet 4.6 against the same source; this pass uses GPT-5 via
Codex CLI. Two independent models, identical source data — disagreement
between them is the signal worth surfacing for human review.

Reviewed thread IDs are tracked in .codex-review-state.json so re-runs skip
already-reviewed posts.

CLI:
  python scripts/codex_review.py                       # poll up to 90 min, default 6h lookback
  python scripts/codex_review.py --since-hours 24      # widen window
  python scripts/codex_review.py --wait-minutes 0      # single pass, no wait
  python scripts/codex_review.py --dry-run             # print verdicts, don't post
  python scripts/codex_review.py --thread <id>         # review one specific thread only
  python scripts/codex_review.py --seed-state          # mark all currently-visible threads as reviewed (no codex calls)

Requires DISCORD_BOT_TOKEN + GUILD_ID in env (loaded from
~/Downloads/Claude/nsmt-discord/.env if present), codex CLI on PATH and
logged in via ChatGPT, and bot Message Content Intent enabled.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

STATE_FILE = PROJECT_ROOT / ".codex-review-state.json"
DISCORD_API = "https://discord.com/api/v10"
CHANNEL_NAME = "recap-pipeline"


def _load_env() -> None:
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
    load_team_kb,
    load_story_packet,
)

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
GUILD_ID = os.environ.get("GUILD_ID")

# Verdict styling — match generate_content.py for visual consistency, but
# branded as Codex so reviewers can tell at a glance who said what.
VERDICT_COLORS = {
    "PASS":           0x2ECC71,
    "NEEDS_REVISION": 0xE67E22,
    "FAIL":           0xE74C3C,
    "UNKNOWN":        0x999999,
}
VERDICT_BADGES = {
    "PASS":           "✅ PASS",
    "NEEDS_REVISION": "⚠️ NEEDS_REVISION",
    "FAIL":           "❌ FAIL",
    "UNKNOWN":        "❓ UNKNOWN",
}

# Embed title prefix used by generate_content.post_recap_to_discord —
# we strip this when extracting team name.
RECAP_TITLE_PREFIX = "📝 New Recap Draft — "
# Demo / one-off posts may use other prefixes; the player-feature demo uses:
FEATURE_TITLE_PREFIX = "🎯 Player Feature — "


def discord(method: str, path: str, **kwargs) -> dict | list:
    if not BOT_TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN not set")
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bot {BOT_TOKEN}"
    headers.setdefault("Content-Type", "application/json")
    resp = requests.request(method, f"{DISCORD_API}{path}", headers=headers, timeout=20, **kwargs)
    if resp.status_code >= 400:
        raise RuntimeError(f"Discord {method} {path} → {resp.status_code}: {resp.text[:300]}")
    return resp.json() if resp.text else {}


def find_channel_id(name: str) -> str:
    channels = discord("GET", f"/guilds/{GUILD_ID}/channels")
    for ch in channels:
        if ch.get("name") == name:
            return ch["id"]
    raise RuntimeError(f"Channel #{name} not found in guild {GUILD_ID}")


def list_recent_threads(channel_id: str, since_hours: int) -> list[dict]:
    payload = discord("GET", f"/guilds/{GUILD_ID}/threads/active")
    threads = [t for t in payload.get("threads", []) if t.get("parent_id") == channel_id]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    fresh: list[dict] = []
    for t in threads:
        created_iso = (t.get("thread_metadata") or {}).get("create_timestamp")
        if not created_iso:
            continue
        try:
            created = datetime.fromisoformat(created_iso.replace("Z", "+00:00"))
        except ValueError:
            continue
        if created >= cutoff:
            fresh.append(t)
    fresh.sort(key=lambda t: (t.get("thread_metadata") or {}).get("create_timestamp", ""))
    return fresh


def get_starter_message(thread_id: str) -> dict | None:
    try:
        return discord("GET", f"/channels/{thread_id}/messages/{thread_id}")
    except RuntimeError:
        msgs = discord("GET", f"/channels/{thread_id}/messages?limit=100")
        if not msgs:
            return None
        return sorted(msgs, key=lambda m: m["timestamp"])[0]


def post_thread_reply(thread_id: str, embed: dict) -> dict:
    return discord("POST", f"/channels/{thread_id}/messages", json={"embeds": [embed]})


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {"reviewed_thread_ids": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def parse_article_from_message(msg: dict) -> dict | None:
    """Pull article fields out of a recap embed produced by
    generate_content.post_recap_to_discord or the player-feature demo."""
    embeds = msg.get("embeds") or []
    if not embeds:
        return None
    e = embeds[0]
    raw_title = (e.get("title") or "").strip()
    title = raw_title
    for prefix in (RECAP_TITLE_PREFIX, FEATURE_TITLE_PREFIX):
        if raw_title.startswith(prefix):
            title = raw_title[len(prefix):].strip()
            break
    body = e.get("description") or ""
    byline = ""
    in_line_verdict = ""
    for f in e.get("fields") or []:
        name = f.get("name", "")
        value = f.get("value", "")
        if "Byline" in name:
            byline = value.strip()
        elif "Fact-check" in name:
            in_line_verdict = value.strip()
    if not title or not body:
        return None
    return {
        "title": title,
        "body": body.strip(),
        "byline": byline,
        "in_line_verdict": in_line_verdict,
    }


def find_team_for_thread(thread: dict, article: dict) -> dict | None:
    """Identify the team this article is about. Forum thread name is set by
    generate_content.post_recap_to_discord as `{team['name']} — {YYYY-MM-DD}`;
    fall back to the embed title (which equals `{team['name']}` for recaps)
    or byline persona for one-off demos."""
    thread_name = (thread.get("name") or "").strip()
    name_from_thread = thread_name.split(" — ")[0].strip() if " — " in thread_name else thread_name
    candidates = [name_from_thread, article["title"], article.get("byline", "")]
    for cand in candidates:
        if not cand:
            continue
        for team in ALL_TEAMS:
            if team["name"].lower() in cand.lower():
                return team
        # match by persona inside byline (e.g. "Sibyl Avery (AI · NSMT)")
        for team in ALL_TEAMS:
            persona = (team.get("persona") or "").strip()
            if persona and persona.lower() in cand.lower():
                return team
    return None


def parse_date_from_thread_name(name: str) -> date | None:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", name or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def review_with_codex(article: dict, team: dict, kb: dict | None, packet: dict | None) -> str:
    """Codex pass that web-verifies each factual claim in the article.

    Unlike the in-line Sonnet pass, this one uses Codex CLI's GPT-5 with web
    search to verify against authoritative sources (ESPN, league-official,
    team-official sites). Same 4-tier claim grading as fact_check_article.
    """
    source_data = json.dumps(
        {"team": team.get("name"), "kb": kb or {}, "packet": packet or {}},
        indent=2,
        default=str,
    )
    prompt = f"""You are a meticulous sports fact-checker. You are paid to find errors, not approve articles. You have web access — USE IT to verify claims, don't just check whether they appear in the source data block.

This is an independent second-opinion pass — the in-line Sonnet 4.6 fact-check has already run and its verdict is on the original Discord embed. Run a fresh, fully independent review; do not anchor to or against the prior verdict.

You have TWO sources of truth:
1. Structured source data (JSON below) — the team KB + any story packet the writer was handed. This is the data the writer was supposed to draw from.
2. The open internet. Authoritative sources for sports facts in priority order: ESPN.com, the league's official site (WNBA.com / NBA.com / NHL.com / NFL.com / MLB.com / MLS / NWSL / UFL), the team's official site, Basketball-Reference / Pro-Football-Reference / Baseball-Reference. Avoid social media / unsourced wikis as primary sources.

Structured source data (JSON):
```
{source_data}
```

Article:
```
{article["title"]}

{article["body"]}
```

Your job: extract every factual claim in the article (records, scores, stat lines, dates, opponents, venues, player names, scoring runs, win-probability claims, ranking claims, attendance, draft years, career stages, coaching staff, ownership, biographical details). For each claim:

A. Check the structured source data first.
B. If not in source, WEB-SEARCH it. Cite the URL you used.
C. Grade the claim:
   ✅ SUPPORTED                   — verified true (appears in source data OR confirmed via web; cite source)
   ⚠️ OUT_OF_SOURCE_BUT_VERIFIED  — true, but writer pulled from outside the source set we handed them (process note, not a factual error)
   ❓ UNVERIFIED                  — couldn't be confirmed via web search (uncertain, needs human eye)
   ❌ FALSE                       — contradicted by web or source data; demonstrably wrong

A claim is ❌ FALSE only if you actively found contradicting authoritative evidence. If web search returns nothing definitive, the claim is ❓ UNVERIFIED — do NOT mark it ❌ just because it's missing from the structured source data.

Pay particular attention to:
- Career-stage / tenure claims (rookie, first-year, "N games into their career") — verify against team KB notes AND public sources.
- Coach / front-office names — verify against the team's official site.
- Roster discipline — every player named MUST exist on the current roster (cross-check ESPN team page).
- Linescore / quarter splits — verify against ESPN box score for that specific game.
- Per-player stat lines — verify against ESPN box score; do not approve based on plausibility.

Output format (strict — keep this format even after web searches):

VERDICT: PASS | NEEDS_REVISION | FAIL

(PASS = every claim is ✅ or ⚠️. NEEDS_REVISION = at least one ❓ but no ❌. FAIL = at least one ❌.)

CLAIMS:
1. "[exact quote from article]" → ✅/⚠️/❓/❌  [reason + citation, e.g. "ESPN box score confirms 26 pts on 9-15 FG: espn.com/wnba/boxscore/_/gameId/..." or "not found on ESPN, WNBA.com, or mystics.wnba.com"]
2. ...

SUMMARY: 2-3 sentences naming the most serious factual issues, or "no factual issues found" — note ⚠️ process flags separately if relevant.

Do not invent issues. Do not approve a claim just because it sounds plausible. Do not ❌ a claim just because it isn't in the structured source data — if the web confirms it, it's ⚠️ at worst.
"""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as outf:
        out_path = outf.name
    try:
        result = subprocess.run(
            [
                "codex", "exec",
                "--skip-git-repo-check",
                "--sandbox", "read-only",
                "--ephemeral",
                "--color", "never",
                "--output-last-message", out_path,
                "-",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode != 0:
            raise RuntimeError(f"codex exec exit {result.returncode}: {result.stderr[:500]}")
        text = Path(out_path).read_text().strip()
        if not text:
            text = result.stdout.strip()
        return text
    finally:
        try:
            Path(out_path).unlink()
        except OSError:
            pass


def extract_verdict(review_text: str) -> str:
    for line in review_text.splitlines():
        s = line.strip().upper()
        if s.startswith("VERDICT:"):
            v = s.split(":", 1)[1].strip()
            if v.startswith("PASS"):
                return "PASS"
            if "FAIL" in v:
                return "FAIL"
            if "NEEDS_REVISION" in v or "NEEDS REVISION" in v:
                return "NEEDS_REVISION"
            break
    return "UNKNOWN"


def build_review_embed(article: dict, team: dict, review_text: str) -> dict:
    verdict = extract_verdict(review_text)
    body = review_text
    MAX = 3800
    if len(body) > MAX:
        body = body[:MAX].rstrip() + "…"
    fields = [
        {"name": "🔍 Reviewer",  "value": "GPT-5 via Codex CLI (ChatGPT subscription)", "inline": False},
        {"name": "Verdict",      "value": VERDICT_BADGES.get(verdict, verdict),         "inline": True},
        {"name": "Source basis", "value": "Same KB + story packet the writer saw",      "inline": True},
    ]
    in_line = article.get("in_line_verdict", "")
    if in_line:
        fields.append({"name": "Sonnet verdict (for comparison)", "value": in_line, "inline": False})
    return {
        "title":       f"🤖 Codex second-opinion review — {team.get('name', article['title'])[:200]}",
        "description": f"```\n{body}\n```",
        "color":       VERDICT_COLORS.get(verdict, 0x999999),
        "fields":      fields,
        "footer":      {"text": "Independent of in-line Sonnet 4.6 fact-check · disagreements warrant human review"},
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    }


def review_thread(thread: dict, *, dry_run: bool) -> str:
    thread_id = thread["id"]
    thread_name = thread.get("name", "(untitled)")
    msg = get_starter_message(thread_id)
    if not msg:
        return f"  - {thread_name} → no starter message, skipped"
    article = parse_article_from_message(msg)
    if not article:
        return f"  - {thread_name} → no parseable embed, skipped"
    team = find_team_for_thread(thread, article)
    if not team:
        return f"  - {thread_name} → could not identify team from thread/embed, skipped"
    target_date = parse_date_from_thread_name(thread_name) or date.today()
    print(f"  · {thread_name}: loading KB + packet for {team['name']} on {target_date}, then invoking codex (~30-90s)…")
    kb = load_team_kb(team)
    packet = load_story_packet(team, target_date)
    review = review_with_codex(article, team, kb, packet)
    if dry_run:
        print(f"\n----- dry-run review for {thread_name} -----\n{review}\n")
        return f"  ✓ {thread_name} → dry-run, not posted"
    embed = build_review_embed(article, team, review)
    post_thread_reply(thread_id, embed)
    return f"  ✓ {thread_name} → {extract_verdict(review)} posted as reply"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-hours", type=int, default=6)
    ap.add_argument("--wait-minutes", type=int, default=90)
    ap.add_argument("--poll-seconds", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--thread", default=None, help="Review one specific thread ID and exit.")
    ap.add_argument("--seed-state", action="store_true",
                    help="Mark all currently-visible threads (within --since-hours) as reviewed without calling codex. Use once to bootstrap before the first real run.")
    args = ap.parse_args()

    if not BOT_TOKEN or not GUILD_ID:
        print("ERROR: DISCORD_BOT_TOKEN and GUILD_ID must be set.", file=sys.stderr)
        return 2

    channel_id = find_channel_id(CHANNEL_NAME)
    print(f"[codex-review] channel #{CHANNEL_NAME} → {channel_id}")
    state = load_state()
    reviewed = set(state.get("reviewed_thread_ids", []))

    if args.seed_state:
        candidates = list_recent_threads(channel_id, args.since_hours)
        for t in candidates:
            reviewed.add(t["id"])
        state["reviewed_thread_ids"] = sorted(reviewed)
        save_state(state)
        print(f"[codex-review] seeded state with {len(candidates)} thread IDs from the last {args.since_hours}h. exiting.")
        return 0

    if args.thread:
        threads: list[dict] = [{"id": args.thread, "name": f"thread {args.thread}"}]
    else:
        deadline = time.monotonic() + max(0, args.wait_minutes) * 60
        threads = []
        while True:
            candidates = list_recent_threads(channel_id, args.since_hours)
            threads = [t for t in candidates if t["id"] not in reviewed]
            if threads or args.wait_minutes == 0 or time.monotonic() >= deadline:
                break
            remaining = int(deadline - time.monotonic())
            print(f"[codex-review] no new articles yet; sleeping {args.poll_seconds}s ({remaining}s left in wait window)")
            time.sleep(args.poll_seconds)

    if not threads:
        print("[codex-review] no unreviewed articles in window. exiting.")
        return 0

    print(f"[codex-review] {len(threads)} thread(s) to review:")
    for t in threads:
        try:
            result = review_thread(t, dry_run=args.dry_run)
            print(result)
            if not args.dry_run and result.startswith("  ✓"):
                reviewed.add(t["id"])
        except Exception as e:
            print(f"  ! {t.get('name','?')} → {type(e).__name__}: {e}")

    if not args.dry_run:
        state["reviewed_thread_ids"] = sorted(reviewed)
        save_state(state)
    print("[codex-review] done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
