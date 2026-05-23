#!/usr/bin/env python3
"""Three-model comparison harness — same Nationals topic, three writers.

Runs the same season-feature prompt (Topic #4: "The Nationals at 50 Games")
through Haiku 4.5, Sonnet 4.6, and Opus 4.7 in sequence. For each model:

  1. Generate article via Anthropic API with web_search enabled (max_uses=5)
  2. Wait 20s (rate-limit cooldown — we hit a 429 on 2026-05-22 doing
     back-to-back writer+fact-check calls)
  3. Run the IN-LINE fact-check (Sonnet 4.6 + web_search) — same checker
     for all three so the comparison is about writer quality, not checker
     quality
  4. Save local draft to drafts/nationals-season-{model_slug}-{ts}.md
  5. Post to Discord with the model name in the thread title (so each
     shows up as a distinct comparable thread in #recap-pipeline)
  6. Wait 20s before the next model

After all 3 finish, prints a side-by-side comparison table and
(optionally) posts the table as a final summary embed.

Codex second-opinion review is NOT triggered from this script — run
scripts/codex_review.py locally after the comparison so it picks up the
3 new threads and posts a verdict reply to each. Codex CLI is local-only
(uses your ChatGPT subscription), so the GH Actions runner can't reach it.

CLI:
  python scripts/compare_models.py                     # run all 3 + post to Discord
  python scripts/compare_models.py --no-discord        # local drafts only
  python scripts/compare_models.py --models haiku      # subset, e.g. just one
  python scripts/compare_models.py --models haiku,sonnet
  python scripts/compare_models.py --stop-after sonnet # don't run Opus
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _load_env() -> None:
    for env_path in [PROJECT_ROOT / ".env", Path.home() / "Downloads/Claude/nsmt-discord/.env"]:
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
    FACT_CHECK_MAX_WEB_SEARCHES,
    GUARDRAILS,
    NSMT_BLUE,
    _parse_verdict,
    _SOURCE_HIERARCHY_RULE,
    _VERDICT_BADGES,
    _VERDICT_COLORS,
    build_byline,
    consume_story_packet,
    fact_check_article,
    kb_context_block,
    load_story_packet,
    load_team_kb,
)


# ── Model registry ────────────────────────────────────────────────────────────

MODEL_REGISTRY = {
    "haiku":  {
        "id":   "claude-haiku-4-5-20251001",
        "name": "Haiku 4.5",
        "max_tokens": 2048,
    },
    "sonnet": {
        "id":   "claude-sonnet-4-6",
        "name": "Sonnet 4.6",
        "max_tokens": 2048,
    },
    "opus":   {
        "id":   "claude-opus-4-7",
        "name": "Opus 4.7",
        "max_tokens": 2048,
    },
}

# Writer call's web_search cap. Mirrors generate_content.WRITER_MAX_WEB_SEARCHES;
# kept locally so this script doesn't need to re-import the constant. Lowered
# from 5 → 2 on 2026-05-22 to ease free-tier TPM pressure.
WRITER_MAX_WEB_SEARCHES = 2

# Intra-model cooldown — between a model's writer call and its own fact-
# check call. We hit 429s with 20s on 2026-05-22; 60s is the safer default
# to let TPM drain between two heavy Sonnet+web_search calls.
INTER_CALL_COOLDOWN_SEC = 60

# Inter-model cooldown — between models. Heavier than intra because each
# model just consumed tokens for writer + fact-check. 300s (5 min) is a
# safe default for tier-limited Anthropic accounts.
DEFAULT_INTER_MODEL_COOLDOWN_SEC = 300


# ── Season-feature prompt (topic #4) ──────────────────────────────────────────

TOPIC_TITLE_HINT = "The Nationals at 50 Games: What 25-27 Tells Us About Year One of the Reset"

TOPIC_PROMPT_FRAME = """
Frame for this article (use your own structure, but cover all of it):

- 50 games into the 2026 season. The Nationals' record is in the Verified team context above —
  cite it. Their home/away split (from the same source) is worth using.
- Year one of a new leadership group. Manager Blake Butera (33, first-year MLB manager,
  hired October 2025), GM Ani Kilambi (hired December 2025 from Philadelphia), and President
  of Baseball Operations Paul Toboni (hired September 2025 from Boston) all came in after
  Davey Martinez + Mike Rizzo were fired in July 2025. The Verified team context has the
  hire details — do NOT invent additional biographical color about these executives.
- The young position-player core: CJ Abrams (SS), James Wood (RF), Dylan Crews (CF). Stats
  worth using are in their roster notes. Crews is returning from an injury per his note.
- Recent form: KB has the last several games. Don't pretend to know any game outside that list.
- What's worth watching the rest of the way — kept hedged. We're 50 games in; declaring a team's
  identity from this sample violates ANTI-OVERCLAIM.

Voice / structure:
- 800-1000 words. Flowing paragraphs only — no headers, no bullets.
- Stays in your persona's voice.
- The opening line shouldn't be a record summary — find a more interesting hook (the leadership
  change story, a specific player's contribution, the home/away split, the schedule shape).
- The close should be forward-looking but appropriately hedged.

Output format:
- The very first line of your response must start with `TITLE:` — your headline (one line,
  sentence case, no clickbait). The headline at the top of this prompt is a hint, not a mandate.
- The very last line of your response must start with `EXCERPT:` — a one-sentence teaser
  (max 160 characters) for the article preview.
"""


def build_season_prompt(team: dict, kb: dict, packet: dict | None) -> str:
    persona_name  = team.get("persona") or "an NSMT writer"
    persona_voice = team.get("voice") or "professional and engaging"
    kb_block = kb_context_block(kb)
    packet_block = consume_story_packet(packet) if packet else ""
    return (
        f"You are {persona_name}, an AI sports writer for NSMT (Nova Sports Media Team), "
        f"the DMV's premier independent sports media outlet covering Washington DC, Maryland, "
        f"and Virginia. NSMT is transparent that you are an AI — readers know your byline is "
        f"AI-authored. Your voice: {persona_voice}.\n"
        f"{kb_block}{packet_block}\n"
        f"\nWrite a season-check-in feature on the {team['name']}. Title hint (use or "
        f"replace): \"{TOPIC_TITLE_HINT}\"\n"
        f"{TOPIC_PROMPT_FRAME}\n\n"
        f"Editorial guardrails (HARD requirements):\n"
        f"{GUARDRAILS}\n"
        f"{_SOURCE_HIERARCHY_RULE}\n"
    )


# ── Anthropic call with retry-on-429 ─────────────────────────────────────────

def call_anthropic(model_id: str, prompt: str, max_tokens: int = 2048,
                   with_web_search: bool = True, max_retries: int = 3) -> tuple[str, dict]:
    """Returns (full_text, meta). meta has model, retries, elapsed_seconds.
    Retries up to `max_retries` times on 429 with exponential backoff."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set in env")
    body: dict = {
        "model":      model_id,
        "max_tokens": max_tokens,
        "messages":   [{"role": "user", "content": prompt}],
    }
    if with_web_search:
        body["tools"] = [{
            "type":     "web_search_20250305",
            "name":     "web_search",
            "max_uses": WRITER_MAX_WEB_SEARCHES,
        }]
    start = time.time()
    last_exc = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key":         ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type":      "application/json",
                },
                json=body,
                timeout=240,
            )
            if resp.status_code == 429:
                backoff = 30 * (2 ** attempt)  # 30s, 60s, 120s
                print(f"    429 rate-limit; sleeping {backoff}s before retry {attempt + 1}/{max_retries}")
                time.sleep(backoff)
                continue
            resp.raise_for_status()
            blocks = resp.json().get("content", [])
            text_chunks = [b["text"] for b in blocks if b.get("type") == "text"]
            elapsed = time.time() - start
            return ("\n\n".join(text_chunks).strip(),
                    {"model": model_id, "retries": attempt, "elapsed_sec": round(elapsed, 1)})
        except requests.HTTPError as exc:
            last_exc = exc
            if 500 <= resp.status_code < 600 and attempt < max_retries - 1:
                backoff = 15 * (2 ** attempt)
                print(f"    {resp.status_code} server error; sleeping {backoff}s before retry")
                time.sleep(backoff)
                continue
            raise
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                time.sleep(15)
                continue
            raise
    raise RuntimeError(f"Exhausted retries: {last_exc}")


# ── Parse helpers ─────────────────────────────────────────────────────────────

def split_title_body_excerpt(text: str, default_title: str) -> tuple[str, str, str]:
    title = default_title
    excerpt = ""
    body_lines: list[str] = []
    for line in text.splitlines():
        s = line.strip().strip("*").strip()
        if s.upper().startswith("TITLE:"):
            title = s.split(":", 1)[1].strip().strip('"\'') or default_title
            continue
        if s.upper().startswith("EXCERPT:"):
            excerpt = s.split(":", 1)[1].strip()
            continue
        body_lines.append(line)
    body = "\n".join(body_lines).strip()
    return title, body, excerpt


def word_count(text: str) -> int:
    return len(text.split())


_CLAIM_TIER_PATTERNS = [
    ("supported",  r"✅"),
    ("verified",   r"⚠️"),
    ("editorial",  r"💬"),
    ("unverified", r"❓"),
    ("false",      r"❌"),
]


def count_claim_tiers(report: str) -> dict[str, int]:
    """Count claim-tier emoji marks in a fact-check report. Returns dict with
    keys supported / verified / editorial / unverified / false."""
    out = {label: 0 for label, _ in _CLAIM_TIER_PATTERNS}
    if not report:
        return out
    for label, pattern in _CLAIM_TIER_PATTERNS:
        out[label] = len(re.findall(pattern, report))
    return out


# ── Discord posting ──────────────────────────────────────────────────────────

def post_comparison_thread(team: dict, model_name: str, title: str, body: str,
                            excerpt: str, verdict: str, report: str | None) -> bool:
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
    article_embed = {
        "title":       f"🔬 Compare — {model_name} — {title}",
        "description": body_text,
        "color":       color,
        "fields": [
            {"name": "✍️ Byline",      "value": byline,                "inline": False},
            {"name": "🏆 Team",        "value": team["name"],          "inline": True},
            {"name": "🔍 In-line FC",  "value": badge,                 "inline": True},
            {"name": "🤖 Model",       "value": model_name,            "inline": True},
            {"name": "🧾 Excerpt",     "value": excerpt or "(none)",   "inline": False},
        ],
        "footer":    {"text": f"{team['league']} · 3-model comparison · codex_review will reply"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    # For comparison runs, only send the article embed (verdict is shown in
    # the article embed's fields). The full fact-check report is in the
    # local draft artifact + Codex review will reply separately. Embedding
    # the full FC report alongside the article exceeds Discord's 6000-char
    # combined-embed limit when articles are 800+ words.
    embeds = [article_embed]
    thread_name = f"Compare — {model_name} — {team['name']}"[:99]
    payload = {"thread_name": thread_name, "embeds": embeds}
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
    print(f"  ✓ Discord post created ({len(embeds)} embed(s))")
    return True


# ── Per-model run ────────────────────────────────────────────────────────────

def run_model(model_key: str, team: dict, kb: dict, packet: dict | None,
              args) -> dict:
    """Run the writer + fact-check for one model. Returns a result dict."""
    spec = MODEL_REGISTRY[model_key]
    print(f"\n[{spec['name']}] generating article…")
    prompt = build_season_prompt(team, kb, packet)

    write_start = time.time()
    article_text, write_meta = call_anthropic(
        spec["id"], prompt,
        max_tokens=spec["max_tokens"],
        with_web_search=not args.no_web_search,
    )
    write_elapsed = round(time.time() - write_start, 1)
    print(f"[{spec['name']}] writer: {write_elapsed}s, {len(article_text)} chars, retries={write_meta['retries']}")

    title, body, excerpt = split_title_body_excerpt(
        article_text, default_title=TOPIC_TITLE_HINT
    )
    words = word_count(body)
    print(f"[{spec['name']}] parsed: title={title!r}  words={words}  excerpt={(excerpt or '')[:60]!r}…")

    # Local draft
    drafts_dir = PROJECT_ROOT / "drafts"
    drafts_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    draft_path = drafts_dir / f"nationals-season-{model_key}-{stamp}.md"
    draft_path.write_text(
        f"# {title}\n\n"
        f"**Model:** {spec['name']} (`{spec['id']}`)  \n"
        f"**Words:** {words}  \n"
        f"**Writer time:** {write_elapsed}s  \n"
        f"**Excerpt:** {excerpt}\n\n"
        f"---\n\n{body}\n\n"
    )
    print(f"[{spec['name']}] saved {draft_path.relative_to(PROJECT_ROOT)}")

    # Cooldown before fact-check
    if not args.no_fact_check:
        print(f"[{spec['name']}] sleeping {INTER_CALL_COOLDOWN_SEC}s before fact-check…")
        time.sleep(INTER_CALL_COOLDOWN_SEC)

        print(f"[{spec['name']}] in-line fact-check (Sonnet 4.6 + web_search)…")
        fc_start = time.time()
        verdict, report = fact_check_article(body, kb, packet, team)
        fc_elapsed = round(time.time() - fc_start, 1)
        print(f"[{spec['name']}] fact-check: verdict={verdict} ({fc_elapsed}s)")
        # Append the report to the local draft
        tier_counts = count_claim_tiers(report or "")
        with draft_path.open("a") as f:
            f.write(f"\n---\n\n## In-line fact-check ({spec['name']})\n\n")
            f.write(f"**Verdict:** {verdict}  \n")
            f.write(f"**Tier counts:** ✅{tier_counts['supported']}  "
                    f"⚠️{tier_counts['verified']}  💬{tier_counts['editorial']}  "
                    f"❓{tier_counts['unverified']}  ❌{tier_counts['false']}\n\n")
            f.write(f"```\n{report or '(no report)'}\n```\n")
    else:
        verdict, report, fc_elapsed = "SKIPPED", None, 0
        tier_counts = {l: 0 for l, _ in _CLAIM_TIER_PATTERNS}

    # Discord post
    if not args.no_discord:
        print(f"[{spec['name']}] posting to Discord…")
        post_comparison_thread(team, spec["name"], title, body, excerpt, verdict, report)
    else:
        print(f"[{spec['name']}] --no-discord; skipping post")

    return {
        "model_key":     model_key,
        "model_name":    spec["name"],
        "model_id":      spec["id"],
        "title":         title,
        "words":         words,
        "writer_sec":    write_elapsed,
        "writer_retries": write_meta["retries"],
        "verdict":       verdict,
        "fc_sec":        fc_elapsed,
        "tier_counts":   tier_counts,
        "draft_path":    str(draft_path.relative_to(PROJECT_ROOT)),
    }


# ── Summary ──────────────────────────────────────────────────────────────────

def print_summary(results: list[dict]) -> None:
    print("\n\n=== COMPARISON SUMMARY ===")
    print(f"Topic: {TOPIC_TITLE_HINT}")
    print()
    header = f"  {'Model':12s} {'Words':>5s} {'Verdict':16s} {'✅':>3s} {'⚠️':>3s} {'💬':>3s} {'❓':>3s} {'❌':>3s} {'Time':>6s}"
    print(header)
    print("  " + "─" * (len(header) - 2))
    for r in results:
        t = r["tier_counts"]
        time_str = f"{r['writer_sec']}+{r['fc_sec']}s"
        print(f"  {r['model_name']:12s} {r['words']:5d} {r['verdict']:16s} "
              f"{t['supported']:3d} {t['verified']:3d} {t['editorial']:3d} "
              f"{t['unverified']:3d} {t['false']:3d} {time_str:>6s}")
    print()
    print("Next step: run scripts/codex_review.py --since-hours 1 --wait-minutes 0")
    print("           to get the Codex second-opinion verdict on each thread.")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="3-model Nationals comparison harness.")
    parser.add_argument("--models", default="haiku,sonnet,opus",
                        help="Comma-separated subset of {haiku,sonnet,opus} (default: all).")
    parser.add_argument("--stop-after", default=None,
                        help="Run up through this model and stop (e.g. 'sonnet' to skip Opus).")
    parser.add_argument("--no-discord",    action="store_true")
    parser.add_argument("--no-fact-check", action="store_true")
    parser.add_argument("--no-web-search", action="store_true",
                        help="Disable web_search at the writer (still on for fact-check).")
    parser.add_argument("--date", default="2026-05-21",
                        help="Story-packet date (YYYY-MM-DD).")
    parser.add_argument("--inter-model-cooldown", type=int,
                        default=DEFAULT_INTER_MODEL_COOLDOWN_SEC,
                        help="Seconds to sleep between models (default 300 = 5 min). "
                             "Avoids cumulative TPM exhaustion on tier-limited accounts.")
    args = parser.parse_args()

    requested = [m.strip().lower() for m in args.models.split(",") if m.strip()]
    for m in requested:
        if m not in MODEL_REGISTRY:
            print(f"ERROR: unknown model {m!r}. Valid: {list(MODEL_REGISTRY)}", file=sys.stderr)
            return 2
    if args.stop_after:
        if args.stop_after not in MODEL_REGISTRY:
            print(f"ERROR: invalid --stop-after {args.stop_after!r}", file=sys.stderr)
            return 2
        cut = requested.index(args.stop_after) + 1 if args.stop_after in requested else len(requested)
        requested = requested[:cut]

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set in env.", file=sys.stderr)
        return 2

    team = next(t for t in ALL_TEAMS if t["name"] == "Washington Nationals")
    kb = load_team_kb(team)
    packet_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    packet = load_story_packet(team, packet_date)

    print("=" * 60)
    print(f"3-MODEL COMPARISON — {team['name']}")
    print(f"Topic:    {TOPIC_TITLE_HINT}")
    print(f"Models:   {', '.join(requested)}")
    print(f"KB:       {'loaded' if kb else 'MISSING'}")
    print(f"Packet:   {('present (' + args.date + ')') if packet else 'absent (' + args.date + ')'}")
    print("=" * 60)

    results: list[dict] = []
    for i, key in enumerate(requested):
        try:
            r = run_model(key, team, kb, packet, args)
            results.append(r)
        except Exception as e:
            print(f"\n[{key}] FAILED with {type(e).__name__}: {e}")
            results.append({
                "model_key":   key,
                "model_name":  MODEL_REGISTRY[key]["name"],
                "title":       f"(failed: {type(e).__name__})",
                "words":       0,
                "writer_sec":  0,
                "verdict":     "ERROR",
                "fc_sec":      0,
                "tier_counts": {l: 0 for l, _ in _CLAIM_TIER_PATTERNS},
                "draft_path":  "—",
            })
        if i < len(requested) - 1:
            print(f"\n... sleeping {args.inter_model_cooldown}s before next model …")
            time.sleep(args.inter_model_cooldown)

    print_summary(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
