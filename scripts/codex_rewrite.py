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
import re
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
                    body_path: Path, article_type: str,
                    v1_verdict: str, v2_verdict: str,
                    corrections_summary_path: Path,
                    review_trail_path: Path) -> None:
    subprocess.run(
        ["gh", "workflow", "run", PUBLISH_WF, "-R", REPO,
         "-f", f"team={team}",
         "-f", f"date={date_}",
         "-f", f"title={title}",
         "-f", f"excerpt={excerpt}",
         "-f", f"type={article_type}",
         "-f", f"v1_verdict={v1_verdict}",
         "-f", f"v2_verdict={v2_verdict}",
         "-F", f"body=@{body_path}",
         "-F", f"corrections_summary=@{corrections_summary_path}",
         "-F", f"review_trail=@{review_trail_path}"],
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
  ❌ FALSE                       → REWRITE every flagged instance to match the evidence cited in the fact-check report
  ❓ UNVERIFIED                  → SOFTEN every flagged instance ("according to reports", "appears to", "early indication") OR drop them if they can't be softened gracefully
  ⚠️ OUT_OF_SOURCE_BUT_VERIFIED  → LEAVE ALONE (verified true, just not in source data)
  💬 EDITORIAL                   → LEAVE ALONE (subjective judgment)
  ✅ SUPPORTED                   → LEAVE ALONE

**CRITICAL — RESTATED FACTS:** The fact-check report groups each underlying fact under ONE claim with multiple INSTANCES listed (e.g. a single ❌ FALSE claim about "Quinn's tenure" may list both "second-year head coach" AND "his second year running this operation" as instances). When you fix a ❌ or ❓ claim, you MUST edit EVERY listed instance — not just the first one quoted. Search the full article for each instance and apply the same correction to all of them. A correction that fixes one mention but leaves the same fact restated elsewhere is a failure.

**CRITICAL — REMOVE SELF-REFERENTIAL CONTENT:** Independently of the fact-check report, scrub the article for ANY meta-commentary about the publication, the byline, the act of writing, or future coverage plans. Phrases like "NSMT is adding this team to coverage," "this is our first piece," "we'll be following," "at the time of this writing," "in this article," "stay tuned for more from NSMT" — REMOVE the sentence entirely. Do NOT soften ("NSMT appears to be adding..."). REMOVE. The article should read as pure sports content that could appear on ESPN.com — no mention of the outlet, the writer, or the writing process. Open the article with the actual sports story, not with framing about coverage.

Output FORMAT — return BOTH sections in this exact structure, with the literal markers:

=== CORRECTED_ARTICLE_BEGIN ===
[the corrected article body, paragraph breaks preserved, with the EXCERPT: line at the end if the original had one]
=== CORRECTED_ARTICLE_END ===

=== CORRECTIONS_SUMMARY_BEGIN ===
[bullet list of what you changed; one bullet per change. Use this shape, exact verbatim quotes where possible:
- Fixed: "<original phrase>" → "<corrected phrase>" — <one-line reason citing the evidence>
- Softened: "<original phrase>" → "<corrected phrase>" — <one-line reason>
- Removed: "<original phrase>" — <one-line reason>
If you made no changes, output a single line: "No changes — article already passes fact-check."]
=== CORRECTIONS_SUMMARY_END ===

Hard rules:
- The CORRECTED_ARTICLE section is the publishable body, nothing else. No code fences, no preface, no annotations in the prose.
- Do NOT add citations, footnotes, or "(corrected: ...)" markers into the article body itself.
- Do NOT add new claims or new paragraphs.
- The CORRECTIONS_SUMMARY is for human + AI review only — write it in plain markdown bullets.

ARTICLE:
---
{article}
---

FACT-CHECK REPORT:
---
{report}
---

Now output both sections in the required format."""


_ARTICLE_RE  = re.compile(r"=== CORRECTED_ARTICLE_BEGIN ===\s*(.*?)\s*=== CORRECTED_ARTICLE_END ===", re.DOTALL)
_SUMMARY_RE  = re.compile(r"=== CORRECTIONS_SUMMARY_BEGIN ===\s*(.*?)\s*=== CORRECTIONS_SUMMARY_END ===", re.DOTALL)


def codex_rewrite(article_body: str, factcheck_report: str) -> tuple[str, str]:
    """Returns (corrected_body, corrections_summary). If the model output is
    missing one of the sections, falls back gracefully — corrected_body falls
    back to the raw output, corrections_summary falls back to a placeholder."""
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
        text = Path(out_path).read_text().strip() or result.stdout.strip()
    finally:
        try:
            Path(out_path).unlink()
        except OSError:
            pass

    m_art = _ARTICLE_RE.search(text)
    m_sum = _SUMMARY_RE.search(text)
    corrected = m_art.group(1).strip() if m_art else text
    summary   = m_sum.group(1).strip() if m_sum else "(Codex did not return a corrections summary section.)"
    return corrected, summary


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
        # save_local_baseline_draft writes a frontmatter block:
        #   # {title}\n\n**Team:** ...\n**Date:** ...\n\n---\n\n{body}
        # Strip everything before (and including) the first --- separator so
        # only the article prose flows through. Falls back to "strip the title
        # line" for files without the separator.
        if "\n---\n" in raw:
            body = raw.split("\n---\n", 1)[1].lstrip()
        else:
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
        print(f"  · {label}: fact-check v1 '{title[:60]}' (~2-5 min at xhigh)…")
        v1_verdict, v1_report = codex_factcheck(body, title, team)
        print(f"  · {label}: v1 verdict {v1_verdict}")

        if v1_verdict == "PASS":
            corrected = body
            v2_verdict = "PASS"
            v2_report = "(v1 passed — no rewrite needed)"
            corrections_summary = "No changes — article already passes fact-check on first pass."
            print(f"  · {label}: PASS on v1 — no rewrite needed")
        else:
            print(f"  · {label}: rewriting (~3-10 min at xhigh)…")
            corrected, corrections_summary = codex_rewrite(body, v1_report)
            if excerpt and "EXCERPT:" not in corrected:
                corrected = f"{corrected.rstrip()}\n\nEXCERPT: {excerpt}\n"
            print(f"  · {label}: fact-check v2 of corrected body (~2-5 min)…")
            v2_verdict, v2_report = codex_factcheck(corrected, title, team)
            print(f"  · {label}: v2 verdict {v2_verdict}")

        body_path = dest / "corrected.md"
        body_path.write_text(corrected)

        # Persist the corrections summary and the full review trail for both
        # the publish workflow's Discord embed (short summary) and the
        # publish artifact (full trail for AI feedback / audit).
        corrections_path = dest / "corrections_summary.md"
        corrections_path.write_text(corrections_summary)

        trail_path = dest / "review_trail.md"
        trail_lines = [
            f"# Codex review trail — {title}",
            "",
            f"- Team: {team['name']} ({meta['team_slug']})",
            f"- Date: {meta['article_date']}",
            f"- Source workflow: {run['_workflow']} (run {run_id})",
            f"- v1 verdict (Sonnet draft):    **{v1_verdict}**",
            f"- v2 verdict (after rewrite):   **{v2_verdict}**",
            "",
            "## Corrections summary (Codex)",
            "",
            corrections_summary,
            "",
            "## v1 fact-check (full report on Sonnet draft)",
            "",
            v1_report,
            "",
            "## v2 fact-check (full report on corrected body)",
            "",
            v2_report,
            "",
            "## Sonnet draft v1 (original)",
            "",
            body,
            "",
            "## Corrected v2 (published)",
            "",
            corrected,
            "",
        ]
        trail_path.write_text("\n".join(trail_lines))

        if dry_run:
            print(f"\n----- dry-run review trail for {label} -----")
            print(trail_path.read_text()[:3000])
            print(f"----- (truncated at 3000 chars) -----\n")
            return f"  ✓ {label}: dry-run, publish skipped (v1={v1_verdict}, v2={v2_verdict})"

        print(f"  · {label}: triggering {PUBLISH_WF}…")
        trigger_publish(
            team=meta["team_slug"],
            date_=meta["article_date"],
            title=title,
            excerpt=excerpt,
            body_path=body_path,
            article_type=meta["article_type"],
            v1_verdict=v1_verdict,
            v2_verdict=v2_verdict,
            corrections_summary_path=corrections_path,
            review_trail_path=trail_path,
        )
        return f"  ✓ {label}: published (v1={v1_verdict} → v2={v2_verdict})"


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
