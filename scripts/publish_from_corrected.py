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
import os
import sys
from datetime import date
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from generate_content import (  # noqa: E402
    ALL_TEAMS,
    team_slug,
    slugify,
    build_byline,
    NSMT_BLUE,
    ADMIN_REVIEW_URL,
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


def _team_webhook_url(team: dict) -> str | None:
    """If the env exposes DISCORD_<TEAM_SLUG_UPPER>_WEBHOOK_URL, use that
    direct webhook (skips worker). Lets specific teams route to their own
    channel without per-team worker config."""
    slug = (team_slug(team) or "").upper().replace("-", "_")
    if not slug:
        return None
    return os.environ.get(f"DISCORD_{slug}_WEBHOOK_URL")


def _post_direct_webhook(webhook_url: str, embed: dict) -> None:
    r = requests.post(webhook_url, json={"embeds": [embed]}, timeout=15)
    r.raise_for_status()


def _build_direct_baseline_embed(team: dict, title: str, excerpt: str, date_: date) -> dict:
    persona = team.get("persona") or "NSMT Staff"
    byline = build_byline(team)
    desc_parts = []
    if excerpt:
        desc_parts.append(excerpt)
    desc_parts.append(f"**Article:** {title}")
    desc_parts.append(f"**Byline:** {byline}")
    desc_parts.append(f"**Date:** {date_.isoformat()}")
    desc_parts.append(f"[Review in admin]({ADMIN_REVIEW_URL})")
    return {
        "title": f"📝 New baseline draft — {team['name']}",
        "description": "\n".join(desc_parts),
        "color": NSMT_BLUE,
    }


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

    direct_webhook = _team_webhook_url(team)

    if args.type == "baseline":
        article_slug = build_baseline_slug(team, target_date)
        html_body = paragraphs_to_html(body)
        blog_id = save_baseline_to_nsmt(args.title, article_slug, html_body, team, token)
        if not blog_id:
            print("ERROR: admin save failed.", file=sys.stderr)
            return 4
        print(f"  ✓ Saved to admin: BLOG#{blog_id}")
        try:
            if direct_webhook:
                embed = _build_direct_baseline_embed(team, args.title, args.excerpt, target_date)
                _post_direct_webhook(direct_webhook, embed)
                print(f"  ✓ Posted to team-direct webhook (#{team_slug(team)})")
            else:
                post_baseline_to_discord(args.title, args.excerpt, team, "offseason_outlook", target_date)
                print(f"  ✓ Posted to worker target {team.get('channel_target', 'RECAPS')!r}")
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
        minimal_summary = {"score": args.title.split("|")[0].strip(), "venue": "", "opponent": ""}
        try:
            if direct_webhook:
                # Reuse baseline-style embed for direct routing — keeps the
                # team-direct channel feed visually consistent regardless of
                # article type.
                embed = _build_direct_baseline_embed(team, args.title, args.excerpt, target_date)
                _post_direct_webhook(direct_webhook, embed)
                print(f"  ✓ Posted to team-direct webhook (#{team_slug(team)})")
            else:
                post_recap_to_discord(
                    args.title, body, team, minimal_summary, target_date,
                    fact_verdict="UNKNOWN", fact_report=None,
                )
                print(f"  ✓ Posted to worker target {team.get('channel_target', 'RECAPS')!r}")
        except Exception as exc:
            print(f"  ✗ Discord notification failed (non-fatal): {exc!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
