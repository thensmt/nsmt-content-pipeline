#!/usr/bin/env python3
"""Local-only: second-opinion review of NSMT recap-pipeline articles via Codex CLI.

Uses your ChatGPT subscription (via codex CLI auth), not the OpenAI API.
Polls Discord #recap-pipeline forum threads for new articles posted in the
configured window, runs each through Codex for a fact-check, and posts the
review as a reply inside the same forum thread.

Reviewed thread IDs are tracked in .codex-review-state.json so re-runs skip
already-reviewed posts.

CLI:
  python scripts/codex_review.py                       # poll up to 90 min for new articles
  python scripts/codex_review.py --since-hours 6       # widen lookback window (default 6h)
  python scripts/codex_review.py --wait-minutes 0      # single pass, no wait
  python scripts/codex_review.py --dry-run             # print verdicts to stdout, don't post
  python scripts/codex_review.py --thread <id>         # review one specific thread only

Requires DISCORD_BOT_TOKEN + GUILD_ID in env (loaded from
~/Downloads/Claude/nsmt-discord/.env if present), codex CLI on PATH, and the
bot to have View Channel + Send Messages in Threads on #recap-pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

STATE_FILE = PROJECT_ROOT / ".codex-review-state.json"
DISCORD_API = "https://discord.com/api/v10"
CHANNEL_NAME = "recap-pipeline"

# Persona byline → team for refetching authoritative source data.
# Extend this as new team personas come online.
PERSONA_TO_TEAM = {
    "Sibyl Avery": {
        "slug": "mystics",
        "team_id": "16",
        "team_name": "Washington Mystics",
        "sport": "basketball",
        "league_slug": "wnba",
    },
}


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

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
GUILD_ID = os.environ.get("GUILD_ID")


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
    """Active threads in this forum (Discord auto-archives after inactivity)."""
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
    """For forum threads, the starter post is fetched at /channels/{thread_id}/messages/{thread_id}."""
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
    embeds = msg.get("embeds") or []
    if not embeds:
        return None
    e = embeds[0]
    title = (e.get("title") or "").replace("🟢 DEMO — ", "").strip()
    body = e.get("description") or ""
    persona = ""
    excerpt = ""
    for f in e.get("fields") or []:
        name = f.get("name", "")
        value = f.get("value", "")
        if "Byline" in name:
            persona = value.split("(")[0].strip()
        elif "Excerpt" in name:
            excerpt = value
    if not title or not body:
        return None
    return {"title": title, "body": body, "persona": persona, "excerpt": excerpt}


def fetch_source_packet(persona: str) -> dict | None:
    team = PERSONA_TO_TEAM.get(persona)
    if not team:
        return None
    from ingestion.season_aggregator import fetch_season
    return fetch_season(
        team["team_id"],
        team["team_name"],
        sport=team["sport"],
        league_slug=team["league_slug"],
    )


def review_with_codex(article: dict, source_packet: dict) -> str:
    """Pipe a fact-check prompt to codex exec, return final assistant message."""
    prompt = f"""You are a meticulous sports fact-checker. You are paid to find errors, not approve articles.

Extract every factual claim in the article (records, scores, stat lines, dates, opponents, venues, player names, runs, attendance, win-prob claims, ranking claims). For each, mark it:

  ✅ SUPPORTED   exact match in source data
  ⚠️ AMBIGUOUS  partly supported, slightly off
  ❌ UNSUPPORTED appears nowhere in source data, or contradicts it

Source data (authoritative — from ESPN):
```json
{json.dumps(source_packet, indent=2, default=str)}
```

Article:
```
{article["title"]}

{article["body"]}
```

Output format (strict):

VERDICT: PASS | NEEDS_REVISION | FAIL

CLAIMS:
1. "[exact quote]" → ✅/⚠️/❌  [one-sentence reason; cite source field]
2. ...

NUMERIC FACT-CHECK:
- claim_value → source_value → ✅/❌

SUMMARY: 2-3 sentences naming the most serious issues, or "no significant issues found"

Do not invent issues. Do not be lenient. If a player is named in the article, source data MUST list them.
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


def build_review_embed(article: dict, review_text: str) -> dict:
    verdict_line = next(
        (ln for ln in review_text.splitlines() if ln.strip().upper().startswith("VERDICT:")),
        "VERDICT: (no verdict line)",
    )
    body = review_text
    MAX = 3800
    if len(body) > MAX:
        body = body[:MAX].rstrip() + "…"
    color_map = {"PASS": 0x2ECC71, "NEEDS_REVISION": 0xE67E22, "FAIL": 0xE74C3C}
    color = 0x999999
    for k, v in color_map.items():
        if k in verdict_line.upper():
            color = v
            break
    return {
        "title": f"🤖 Codex second-opinion review — {article['title'][:200]}",
        "description": f"```\n{body}\n```",
        "color": color,
        "fields": [
            {"name": "Reviewer", "value": "GPT-5 via Codex CLI (ChatGPT subscription)", "inline": False},
            {"name": "Verdict", "value": verdict_line.strip(), "inline": False},
        ],
        "footer": {"text": "Independent of Sonnet 4.6 fact-check. Source: ESPN season packet."},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def review_thread(thread: dict, *, dry_run: bool) -> str:
    thread_id = thread["id"]
    title = thread.get("name", "(untitled)")
    msg = get_starter_message(thread_id)
    if not msg:
        return f"  - {title} → no starter message, skipped"
    article = parse_article_from_message(msg)
    if not article:
        return f"  - {title} → no article embed, skipped"
    if article["persona"] not in PERSONA_TO_TEAM:
        return f"  - {title} → unknown persona '{article['persona']}', skipped"
    print(f"  · {title}: fetching source data + invoking codex (this can take ~30-90s)…")
    source = fetch_source_packet(article["persona"])
    if source is None:
        return f"  - {title} → source packet fetch failed, skipped"
    review = review_with_codex(article, source)
    if dry_run:
        print(f"\n----- dry-run review for {title} -----\n{review}\n")
        return f"  ✓ {title} → dry-run, not posted"
    embed = build_review_embed(article, review)
    post_thread_reply(thread_id, embed)
    return f"  ✓ {title} → review posted"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-hours", type=int, default=6, help="Lookback window for fresh threads.")
    ap.add_argument("--wait-minutes", type=int, default=90, help="Max minutes to keep polling if no new articles found. 0 = single pass.")
    ap.add_argument("--poll-seconds", type=int, default=300, help="Sleep between poll attempts inside the wait window.")
    ap.add_argument("--dry-run", action="store_true", help="Print reviews instead of posting them.")
    ap.add_argument("--thread", default=None, help="Review one specific thread ID and exit.")
    args = ap.parse_args()

    if not BOT_TOKEN or not GUILD_ID:
        print("ERROR: DISCORD_BOT_TOKEN and GUILD_ID must be set (loaded from .env or env).", file=sys.stderr)
        return 2

    channel_id = find_channel_id(CHANNEL_NAME)
    print(f"[codex-review] channel #{CHANNEL_NAME} → {channel_id}")
    state = load_state()
    reviewed = set(state.get("reviewed_thread_ids", []))

    if args.thread:
        threads = [{"id": args.thread, "name": f"thread {args.thread}"}]
    else:
        deadline = time.monotonic() + max(0, args.wait_minutes) * 60
        threads: list[dict] = []
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
