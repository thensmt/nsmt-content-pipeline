#!/usr/bin/env python3
"""codex_rewrite.py — Mac orchestrator for the staging publish pipeline.

Polls the #drafts-pre-codex Discord channel for new Sonnet drafts that CI
(draft-baseline.yml / draft-recap.yml) produced. For each new draft:

  1. Downloads the body artifact via `gh run download`
  2. Runs Codex fact-check at xhigh (review_with_codex from codex_review.py)
  3. Runs Codex SURGICAL REWRITE using the fact-check findings — preserves
     Sonnet's voice and structure, fixes only the FALSE claims, softens
     UNVERIFIED ones
  4. Triggers .github/workflows/publish-corrected.yml via `gh workflow run`
     with the corrected body + metadata so CI does the admin POST and
     #recap-pipeline post (publish secrets stay in CI)

Processed run_ids live in `.codex-rewrite-state.json` so re-runs skip drafts
already pushed through.

Requires:
  DISCORD_BOT_TOKEN + GUILD_ID — auto-loaded from .env or ~/Downloads/Claude/nsmt-discord/.env
  codex CLI on PATH, logged in via ChatGPT subscription
  gh CLI on PATH, logged in to thensmt

CLI:
  python scripts/codex_rewrite.py                       # poll up to 90 min, default 6h lookback
  python scripts/codex_rewrite.py --wait-minutes 0      # single pass, no wait
  python scripts/codex_rewrite.py --since-hours 24      # widen window
  python scripts/codex_rewrite.py --run-id 12345        # process one specific run id then exit
  python scripts/codex_rewrite.py --dry-run             # do all the work, but don't trigger publish
  python scripts/codex_rewrite.py --seed-state          # mark all currently visible drafts as done
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

STATE_FILE     = PROJECT_ROOT / ".codex-rewrite-state.json"
DISCORD_API    = "https://discord.com/api/v10"
STAGING_NAME   = "commanders"
DEFAULT_REPO   = "thensmt/nsmt-content-pipeline"
PUBLISH_WF     = "publish-corrected.yml"
EMBED_TITLE_PREFIX = "📥 Pre-codex draft ready"


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

from scripts.codex_review import review_with_codex, extract_verdict  # noqa: E402
from generate_content import ALL_TEAMS, load_team_kb, team_slug  # noqa: E402

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
GUILD_ID  = os.environ.get("GUILD_ID")
REPO      = os.environ.get("NSMT_CONTENT_REPO", DEFAULT_REPO)


# ── State ─────────────────────────────────────────────────────────────────────

def load_state() -> set[str]:
    if not STATE_FILE.exists():
        return set()
    try:
        data = json.loads(STATE_FILE.read_text())
        return set(data.get("processed_run_ids", []))
    except Exception:
        return set()


def save_state(run_ids: set[str]) -> None:
    STATE_FILE.write_text(json.dumps({"processed_run_ids": sorted(run_ids)}, indent=2))


# ── Discord ───────────────────────────────────────────────────────────────────

def discord_get(path: str, **params) -> list | dict:
    r = requests.get(
        f"{DISCORD_API}{path}",
        params=params,
        headers={"Authorization": f"Bot {BOT_TOKEN}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def find_channel_id(name: str) -> str:
    channels = discord_get(f"/guilds/{GUILD_ID}/channels")
    for ch in channels:
        if ch.get("name") == name:
            return ch["id"]
    raise RuntimeError(f"Channel #{name} not found in guild {GUILD_ID}")


def list_recent_staging_messages(channel_id: str, since_hours: int) -> list[dict]:
    """Return messages from #drafts-pre-codex whose embed matches our staging
    notification shape, newest first."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    msgs = discord_get(f"/channels/{channel_id}/messages", limit=50)
    out = []
    for m in msgs:
        try:
            ts = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
        except Exception:
            continue
        if ts < cutoff:
            continue
        embeds = m.get("embeds") or []
        if not embeds:
            continue
        if not (embeds[0].get("title") or "").startswith(EMBED_TITLE_PREFIX):
            continue
        out.append(m)
    return out


def parse_staging_embed(msg: dict) -> dict | None:
    """Pull the metadata fields the GH workflow emitted into the embed."""
    embeds = msg.get("embeds") or []
    if not embeds:
        return None
    fields = {f.get("name"): f.get("value") for f in (embeds[0].get("fields") or [])}
    required = ("team_slug", "article_type", "article_date", "run_id", "artifact_name")
    if not all(k in fields for k in required):
        return None
    # Pull title out of the description (more reliable than embed.title which
    # has emoji + "Pre-codex draft ready — slug" formatting)
    title = ""
    desc = embeds[0].get("description") or ""
    for line in desc.splitlines():
        if line.startswith("**Title:**"):
            title = line.partition("**Title:**")[2].strip()
            break
    return {
        "team_slug":     fields["team_slug"].strip(),
        "article_type":  fields["article_type"].strip(),
        "article_date":  fields["article_date"].strip(),
        "run_id":        fields["run_id"].strip(),
        "artifact_name": fields["artifact_name"].strip(),
        "title":         title,
    }


# ── Artifacts + GH workflow ───────────────────────────────────────────────────

def download_artifact(run_id: str, artifact_name: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["gh", "run", "download", run_id,
         "-R", REPO,
         "-n", artifact_name,
         "--dir", str(dest_dir)],
        check=True,
    )
    md_files = list(dest_dir.rglob("*.md"))
    if not md_files:
        raise RuntimeError(f"No .md file in artifact {artifact_name!r}")
    if len(md_files) > 1:
        print(f"  warn: multiple .md files in artifact, using {md_files[0]}", file=sys.stderr)
    return md_files[0]


def trigger_publish(team: str, date_: str, title: str, excerpt: str,
                    body_path: Path, article_type: str) -> None:
    subprocess.run(
        ["gh", "workflow", "run", PUBLISH_WF, "-R", REPO,
         "-f", f"team={team}",
         "-f", f"date={date_}",
         "-f", f"title={title}",
         "-f", f"excerpt={excerpt}",
         "-f", f"type={article_type}",
         "-F", f"body=@{body_path}"],
        check=True,
    )


# ── Codex calls ───────────────────────────────────────────────────────────────

CODEX_BASE_ARGS = [
    "codex", "exec",
    "--skip-git-repo-check",
    "--sandbox", "read-only",
    "--ephemeral",
    "--color", "never",
    "-c", 'model_reasoning_effort="xhigh"',
]


def codex_factcheck(article_body: str, title: str, team: dict) -> tuple[str, str]:
    """Run the xhigh fact-check pass and return (verdict, full_report)."""
    kb = load_team_kb(team)
    report = review_with_codex(
        {"title": title, "body": article_body},
        team, kb, None,
    )
    return extract_verdict(report), report


CODEX_REWRITE_PROMPT_TMPL = """You are a careful sports copy editor making MINIMAL, SURGICAL fact corrections.

Inputs:
1. An article drafted by another writer. PRESERVE the writer's voice, byline references, paragraph structure, and overall tone. Do not rewrite paragraphs that don't need it.
2. A fact-check report listing each factual claim with a grading symbol.

For each claim graded:
  ❌ FALSE                       → REWRITE that sentence/phrase to match the evidence cited in the fact-check report
  ❓ UNVERIFIED                  → SOFTEN the claim ("according to reports", "appears to", "early indication") OR drop it if it can't be softened gracefully
  ⚠️ OUT_OF_SOURCE_BUT_VERIFIED  → LEAVE ALONE (verified true, just not in source data)
  💬 EDITORIAL                   → LEAVE ALONE (subjective judgment)
  ✅ SUPPORTED                   → LEAVE ALONE

Hard rules:
- Output ONLY the corrected article body. No commentary, no markdown code fences around the whole thing, no "Here's the corrected article" preface.
- Do NOT add citations, footnotes, or "(corrected: ...)" annotations into the prose.
- Do NOT add new claims or new paragraphs.
- Keep the EXCERPT: line at the end of the article if one exists.
- If no FALSE or UNVERIFIED claims need editing, return the article body unchanged.

ARTICLE:
---
{article}
---

FACT-CHECK REPORT:
---
{report}
---

Now output the corrected article body."""


def codex_rewrite(article_body: str, factcheck_report: str) -> str:
    """Invoke codex exec with the surgical-rewrite prompt and return the new body."""
    prompt = CODEX_REWRITE_PROMPT_TMPL.format(article=article_body, report=factcheck_report)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as outf:
        out_path = outf.name
    try:
        result = subprocess.run(
            CODEX_BASE_ARGS + ["--output-last-message", out_path, "-"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=900,                       # 15 min — rewrite at xhigh
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"codex rewrite exit {result.returncode}: {result.stderr[:500]}"
            )
        text = Path(out_path).read_text().strip()
        if not text:
            text = result.stdout.strip()
        return text
    finally:
        try:
            Path(out_path).unlink()
        except OSError:
            pass


# ── Per-draft processing ──────────────────────────────────────────────────────

def find_team_by_slug(slug: str) -> dict | None:
    for t in ALL_TEAMS:
        if (team_slug(t) or "").lower() == slug.lower():
            return t
    return None


def process_staging_msg(msg: dict, *, dry_run: bool) -> str:
    meta = parse_staging_embed(msg)
    if not meta:
        return "  - unparseable embed, skipped"
    team = find_team_by_slug(meta["team_slug"])
    if not team:
        return f"  - team_slug {meta['team_slug']!r} not in ALL_TEAMS, skipped"

    label = f"{meta['team_slug']}@{meta['run_id']}"
    print(f"  · {label}: downloading artifact {meta['artifact_name']}…")
    with tempfile.TemporaryDirectory(prefix="nsmt-rewrite-") as tmp:
        dest = Path(tmp)
        draft_path = download_artifact(meta["run_id"], meta["artifact_name"], dest)
        raw = draft_path.read_text()

        # Strip the leading "# {title}\n\n" that save_local_baseline_draft writes
        lines = raw.splitlines()
        if lines and lines[0].startswith("# "):
            body = "\n".join(lines[1:]).lstrip()
        else:
            body = raw

        # Pull EXCERPT off the bottom if present
        excerpt = ""
        if "EXCERPT:" in body:
            head, _, tail = body.rpartition("EXCERPT:")
            body = head.rstrip()
            excerpt = tail.strip()

        print(f"  · {label}: fact-checking (~2-5 min at xhigh)…")
        verdict, report = codex_factcheck(body, meta["title"], team)
        print(f"  · {label}: fact-check verdict {verdict}")

        # Only rewrite if there's something to fix. PASS articles go through
        # unchanged.
        if verdict == "PASS":
            corrected = body
            print(f"  · {label}: PASS — no rewrite needed")
        else:
            print(f"  · {label}: rewriting (~3-10 min at xhigh)…")
            corrected = codex_rewrite(body, report)
            # Codex might output the EXCERPT line at the end too. If so, leave
            # it; if not, re-attach the original.
            if excerpt and "EXCERPT:" not in corrected:
                corrected = f"{corrected.rstrip()}\n\nEXCERPT: {excerpt}\n"

        body_path = dest / "corrected.md"
        body_path.write_text(corrected)

        if dry_run:
            print(f"\n----- dry-run: corrected body for {label} -----")
            print(corrected[:2000])
            print(f"----- (truncated at 2000 chars) -----\n")
            return f"  ✓ {label}: dry-run, publish skipped"

        print(f"  · {label}: triggering {PUBLISH_WF}…")
        trigger_publish(
            team=meta["team_slug"],
            date_=meta["article_date"],
            title=meta["title"],
            excerpt=excerpt,
            body_path=body_path,
            article_type=meta["article_type"],
        )
        return f"  ✓ {label}: published via {PUBLISH_WF} (verdict {verdict})"


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-hours",  type=int, default=6)
    ap.add_argument("--wait-minutes", type=int, default=90)
    ap.add_argument("--poll-seconds", type=int, default=300)
    ap.add_argument("--dry-run",   action="store_true")
    ap.add_argument("--run-id",    default=None,
                    help="Process one specific GH run_id (must already be visible in the staging channel) and exit.")
    ap.add_argument("--seed-state", action="store_true",
                    help="Mark all currently-visible staging drafts as done without processing. Use once on first install.")
    args = ap.parse_args()

    if not BOT_TOKEN or not GUILD_ID:
        print("ERROR: DISCORD_BOT_TOKEN and GUILD_ID must be set.", file=sys.stderr)
        return 2

    channel_id = find_channel_id(STAGING_NAME)
    print(f"[codex-rewrite] channel #{STAGING_NAME} → {channel_id}")

    processed = load_state()

    if args.seed_state:
        msgs = list_recent_staging_messages(channel_id, args.since_hours)
        for m in msgs:
            meta = parse_staging_embed(m)
            if meta:
                processed.add(meta["run_id"])
        save_state(processed)
        print(f"[codex-rewrite] seeded state with {len(msgs)} staging draft(s).")
        return 0

    if args.run_id:
        msgs = list_recent_staging_messages(channel_id, max(args.since_hours, 168))
        for m in msgs:
            meta = parse_staging_embed(m)
            if meta and meta["run_id"] == args.run_id:
                print(f"[codex-rewrite] processing one-off run_id={args.run_id}")
                print(process_staging_msg(m, dry_run=args.dry_run))
                if not args.dry_run:
                    processed.add(args.run_id)
                    save_state(processed)
                return 0
        print(f"[codex-rewrite] run_id={args.run_id} not visible in last {args.since_hours}h. Try --since-hours 168.")
        return 1

    deadline = time.monotonic() + max(0, args.wait_minutes) * 60
    while True:
        candidates = list_recent_staging_messages(channel_id, args.since_hours)
        pending = []
        for m in candidates:
            meta = parse_staging_embed(m)
            if meta and meta["run_id"] not in processed:
                pending.append(m)

        if pending:
            print(f"[codex-rewrite] {len(pending)} draft(s) to process:")
            for m in reversed(pending):                       # oldest first
                meta = parse_staging_embed(m)
                try:
                    print(process_staging_msg(m, dry_run=args.dry_run))
                    if not args.dry_run:
                        processed.add(meta["run_id"])
                        save_state(processed)
                except subprocess.CalledProcessError as exc:
                    print(f"  ✗ {meta['team_slug']}@{meta['run_id']}: subprocess failed — {exc}")
                except Exception as exc:
                    print(f"  ✗ {meta['team_slug']}@{meta['run_id']}: {exc!r}")

        if args.wait_minutes == 0 or time.monotonic() >= deadline:
            break
        time.sleep(args.poll_seconds)

    print("[codex-rewrite] done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
