#!/usr/bin/env python3
"""codex_rewrite.py — Mac orchestrator for the staging publish pipeline.

Polls GH Actions for new successful runs of `draft-baseline.yml` (and any
future `draft-recap.yml` etc.). For each new draft:

  1. Downloads the body + metadata artifact via `gh run download`
  2. Runs Codex fact-check at xhigh (review_with_codex from codex_review.py)
  3. Runs Codex SURGICAL REWRITE using the fact-check findings — preserves
     the writer's voice, fixes only the FALSE claims, softens UNVERIFIED ones
  4. Triggers .github/workflows/publish-corrected.yml via `gh workflow run`
     with the corrected body + metadata so CI does the admin POST and the
     Discord post (publish secrets stay in CI)

Processed run_ids live in `.codex-rewrite-state.json` so re-runs skip drafts
already pushed through.

Requires:
  codex CLI on PATH, logged in via ChatGPT subscription
  gh   CLI on PATH, logged in to thensmt with repo + workflow scopes

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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

STATE_FILE     = PROJECT_ROOT / ".codex-rewrite-state.json"
DEFAULT_REPO   = "thensmt/nsmt-content-pipeline"
PUBLISH_WF     = "publish-corrected.yml"
SOURCE_WORKFLOWS = ("draft-baseline.yml",)   # workflows to watch for new drafts


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

REPO = os.environ.get("NSMT_CONTENT_REPO", DEFAULT_REPO)


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


# ── GH Actions polling ────────────────────────────────────────────────────────

def list_recent_draft_runs(since_hours: int) -> list[dict]:
    """Return successful runs of any SOURCE_WORKFLOWS from the last N hours,
    newest first. Each row has keys: databaseId, name, workflowName, createdAt."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    rows: list[dict] = []
    for wf in SOURCE_WORKFLOWS:
        out = subprocess.run(
            ["gh", "run", "list",
             "-R", REPO,
             "--workflow", wf,
             "--status", "success",
             "--limit", "30",
             "--json", "databaseId,name,workflowName,createdAt,headBranch"],
            check=True, capture_output=True, text=True,
        )
        for r in json.loads(out.stdout or "[]"):
            try:
                ts = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
            except Exception:
                continue
            if ts < cutoff:
                continue
            r["_workflow"] = wf
            rows.append(r)
    rows.sort(key=lambda r: r["createdAt"], reverse=True)
    return rows


# ── Artifact handling ─────────────────────────────────────────────────────────

def download_artifact_for_run(run_id: str, dest_dir: Path) -> tuple[dict, Path]:
    """Download whatever single artifact this run produced (we publish one per
    run, named nsmt-draft-{team}-{run_id}). Returns (meta_dict, body_path)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    # List artifacts first so we know the name (avoids relying on naming convention).
    out = subprocess.run(
        ["gh", "api", f"repos/{REPO}/actions/runs/{run_id}/artifacts"],
        check=True, capture_output=True, text=True,
    )
    arts = json.loads(out.stdout).get("artifacts", [])
    nsmt_arts = [a for a in arts if a.get("name", "").startswith("nsmt-draft-")]
    if not nsmt_arts:
        raise RuntimeError(f"No nsmt-draft-* artifact on run {run_id}")
    artifact_name = nsmt_arts[0]["name"]
    subprocess.run(
        ["gh", "run", "download", run_id,
         "-R", REPO,
         "-n", artifact_name,
         "--dir", str(dest_dir)],
        check=True,
    )
    meta_paths = list(dest_dir.rglob("_meta/meta.json"))
    if not meta_paths:
        raise RuntimeError(f"Artifact {artifact_name} missing _meta/meta.json")
    meta = json.loads(meta_paths[0].read_text())
    md_files = [p for p in dest_dir.rglob("*.md")]
    if not md_files:
        raise RuntimeError(f"Artifact {artifact_name} missing a .md body file")
    return meta, md_files[0]


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


# ── Per-run processing ────────────────────────────────────────────────────────

def find_team_by_slug(slug: str) -> dict | None:
    for t in ALL_TEAMS:
        if (team_slug(t) or "").lower() == slug.lower():
            return t
    return None


def process_run(run: dict, *, dry_run: bool) -> str:
    run_id = str(run["databaseId"])
    label = f"run {run_id} ({run['_workflow']})"
    print(f"  · {label}: downloading artifact…")
    with tempfile.TemporaryDirectory(prefix="nsmt-rewrite-") as tmp:
        dest = Path(tmp)
        meta, draft_path = download_artifact_for_run(run_id, dest)

        team = find_team_by_slug(meta["team_slug"])
        if not team:
            return f"  - {label}: team_slug {meta['team_slug']!r} unknown, skipped"

        raw = draft_path.read_text()
        lines = raw.splitlines()
        if lines and lines[0].startswith("# "):
            body = "\n".join(lines[1:]).lstrip()
        else:
            body = raw

        excerpt = ""
        if "EXCERPT:" in body:
            head, _, tail = body.rpartition("EXCERPT:")
            body = head.rstrip()
            excerpt = tail.strip()

        title = meta.get("title", "(untitled)")
        print(f"  · {label}: fact-checking '{title[:60]}' (~2-5 min at xhigh)…")
        verdict, report = codex_factcheck(body, title, team)
        print(f"  · {label}: fact-check verdict {verdict}")

        if verdict == "PASS":
            corrected = body
            print(f"  · {label}: PASS — no rewrite needed")
        else:
            print(f"  · {label}: rewriting (~3-10 min at xhigh)…")
            corrected = codex_rewrite(body, report)
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
            title=title,
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
                    help="Process one specific GH run_id and exit.")
    ap.add_argument("--seed-state", action="store_true",
                    help="Mark all currently-visible draft runs as done without processing.")
    args = ap.parse_args()

    print(f"[codex-rewrite] polling {REPO} for {', '.join(SOURCE_WORKFLOWS)}")

    processed = load_state()

    if args.seed_state:
        runs = list_recent_draft_runs(args.since_hours)
        for r in runs:
            processed.add(str(r["databaseId"]))
        save_state(processed)
        print(f"[codex-rewrite] seeded state with {len(runs)} draft run(s).")
        return 0

    if args.run_id:
        print(f"[codex-rewrite] processing one-off run_id={args.run_id}")
        # Build a minimal run dict so process_run can use it
        run = {"databaseId": args.run_id, "_workflow": "draft-baseline.yml"}
        print(process_run(run, dry_run=args.dry_run))
        if not args.dry_run:
            processed.add(str(args.run_id))
            save_state(processed)
        return 0

    deadline = time.monotonic() + max(0, args.wait_minutes) * 60
    while True:
        runs = list_recent_draft_runs(args.since_hours)
        pending = [r for r in runs if str(r["databaseId"]) not in processed]

        if pending:
            print(f"[codex-rewrite] {len(pending)} draft run(s) to process:")
            for r in reversed(pending):                       # oldest first
                run_id = str(r["databaseId"])
                try:
                    print(process_run(r, dry_run=args.dry_run))
                    if not args.dry_run:
                        processed.add(run_id)
                        save_state(processed)
                except subprocess.CalledProcessError as exc:
                    print(f"  ✗ run {run_id}: subprocess failed — {exc}")
                except Exception as exc:
                    print(f"  ✗ run {run_id}: {exc!r}")

        if args.wait_minutes == 0 or time.monotonic() >= deadline:
            break
        time.sleep(args.poll_seconds)

    print("[codex-rewrite] done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
