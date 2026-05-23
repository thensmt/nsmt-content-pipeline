#!/usr/bin/env python3
"""Publish a Codex-corrected article body to admin.thensmt.com + Discord.

Designed to be invoked from .github/workflows/publish-corrected.yml after a
Mac-side codex_rewrite.py pass has produced a revised article body. All
publishing secrets stay in CI; the Mac side only does the codex passes.

CLI:
  python scripts/publish_from_corrected.py \
    --team commanders \
    --date 2026-05-23 \
    --title "Washington Commanders: Season Recap & What's Next" \
    --excerpt "..." \
    --type baseline \
    --body /path/to/corrected-body.md

Article types:
  baseline — uses save_baseline_to_nsmt + post_baseline_to_discord
  recap    — uses save_to_nsmt + post_recap_to_discord (game summary defaults
             to a minimal stub since the original summary is not round-tripped
             through workflow inputs)
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from generate_content import (  # noqa: E402
    ALL_TEAMS,
    team_slug,
    slugify,
    get_nsmt_token,
    save_to_nsmt,
    post_recap_to_discord,
)
from generate_baselines import (  # noqa: E402
    save_baseline_to_nsmt,
    post_baseline_to_discord,
    paragraphs_to_html,
    build_slug as build_baseline_slug,
)


def find_team(slug: str) -> dict:
    for t in ALL_TEAMS:
        if (team_slug(t) or "").lower() == slug.lower():
            return t
    raise SystemExit(f"Unknown team slug: {slug!r}. Known: {sorted({team_slug(t) for t in ALL_TEAMS if team_slug(t)})}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", required=True, help="Team slug (e.g. commanders)")
    ap.add_argument("--date", required=True, help="Article date YYYY-MM-DD")
    ap.add_argument("--title", required=True)
    ap.add_argument("--excerpt", default="")
    ap.add_argument("--type", choices=["baseline", "recap"], required=True)
    ap.add_argument("--body", required=True, help="Path to the corrected markdown body")
    args = ap.parse_args()

    team = find_team(args.team)
    target_date = date.fromisoformat(args.date)
    body = Path(args.body).read_text().strip()
    if not body:
        print(f"ERROR: body file {args.body} is empty.", file=sys.stderr)
        return 2

    print(f"Publishing corrected article — team={team['name']} type={args.type} date={target_date.isoformat()}")
    print(f"  Title: {args.title}")
    print(f"  Body:  {len(body)} chars, {len(body.split())} words")

    token = get_nsmt_token()
    if not token:
        print("ERROR: NSMT admin auth failed.", file=sys.stderr)
        return 3

    if args.type == "baseline":
        article_slug = build_baseline_slug(team, target_date)
        html_body = paragraphs_to_html(body)
        blog_id = save_baseline_to_nsmt(args.title, article_slug, html_body, team, token)
        if not blog_id:
            print("ERROR: admin save failed.", file=sys.stderr)
            return 4
        print(f"  ✓ Saved to admin: BLOG#{blog_id}")
        try:
            post_baseline_to_discord(args.title, args.excerpt, team, "offseason_outlook", target_date)
            print("  ✓ Posted notification to #recap-pipeline")
        except Exception as exc:
            print(f"  ✗ Discord notification failed (non-fatal): {exc!r}")
    else:  # recap
        article_slug = slugify(f"{team['name']}-recap-{target_date.isoformat()}")
        html_body = "".join(f"<p>{p.strip()}</p>" for p in body.split("\n\n") if p.strip())
        saved = save_to_nsmt(args.title, article_slug, html_body, args.excerpt, team, target_date, token)
        if not saved:
            print("ERROR: admin save failed.", file=sys.stderr)
            return 4
        print("  ✓ Saved to admin")
        # post_recap_to_discord wants a game summary dict; for corrected
        # republish we don't carry the original summary, so build a minimal
        # one from what we know. score/venue won't appear in the embed.
        minimal_summary = {"score": args.title.split("|")[0].strip(), "venue": "", "opponent": ""}
        try:
            post_recap_to_discord(
                args.title, body, team, minimal_summary, target_date,
                fact_verdict="UNKNOWN", fact_report=None,
            )
            print("  ✓ Posted to #recap-pipeline")
        except Exception as exc:
            print(f"  ✗ Discord notification failed (non-fatal): {exc!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
