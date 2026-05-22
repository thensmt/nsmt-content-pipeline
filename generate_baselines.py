"""
NSMT Baseline Article Generator — one-shot foundation pieces per beat.

Generates 14 baseline articles (one per AI writer persona) that establish
NSMT's coverage of each team. In-season teams get a "season_so_far" feature;
off-season teams get a "season recap + outlook" piece. Future game recaps
build on these.

CLI:
  python generate_baselines.py --dry-run            # plan-only, no API calls
  python generate_baselines.py                      # real run, all 14 teams
  python generate_baselines.py --team commanders    # one team by slug
  python generate_baselines.py --limit 3            # first N teams
  python generate_baselines.py --no-discord         # skip Discord
  python generate_baselines.py --no-admin           # skip admin save
  python generate_baselines.py --date 2026-05-22    # override "today"

Required env vars (real runs):
  ANTHROPIC_API_KEY     — Claude API key
  NSMT_USERNAME         — admin.thensmt.com email
  NSMT_PASSWORD         — admin.thensmt.com password

Optional:
  DISCORD_PROXY_URL     — Cloudflare Worker URL
  DISCORD_PROXY_SECRET  — shared secret matching worker's SHARED_SECRET
"""

import argparse
import os
import sys
import time
import requests
from datetime import date, datetime, timezone

# Reuse the daily-cron module's helpers verbatim. DO NOT modify that file —
# it's the live production cron. We only import from it.
from generate_content import (
    ALL_TEAMS,
    CATEGORY_IDS,
    LEAGUE_SEASONS,         # noqa: F401  (imported for parity / future use)
    ADMIN_REVIEW_URL,
    NSMT_BLUE,
    DISCORD_TARGET,
    ANTHROPIC_API_KEY,
    DISCORD_PROXY_URL,
    DISCORD_PROXY_SECRET,
    in_season,
    build_byline,
    load_team_kb,
    kb_context_block,
    team_slug,
    get_nsmt_token,
    slugify,
    NSMT_API,
)


# ── Persona helpers ───────────────────────────────────────────────────────────

def persona_first_name(team):
    """'Marcus Bell' → 'Marcus'. Falls back gracefully."""
    persona = team.get("persona") or "NSMT Staff"
    return persona.split()[0]


# ── Prompt templates ──────────────────────────────────────────────────────────

def _record_summary_hint(kb):
    """Single line for the season_so_far prompt — what we actually know."""
    if not kb:
        return "see verified team context above"
    rec = kb.get("current_record")
    if rec:
        return f"current record: {rec}"
    return "see verified team context above"


_BASELINE_GUARDRAILS = (
    "- ANTI-OVERCLAIM: avoid deterministic causality framings from small samples\n"
    "  (<10 games). Use 'early pattern', 'possible trend', 'worth monitoring' —\n"
    "  do not declare team identity from a handful of games.\n"
    "- ANTI-FABRICATION: every stat, date, opponent, score, and player name must\n"
    "  come from the Verified team context above. Do not invent numbers.\n"
    "- NO SOURCE-MIXING: do not blend stats from different sources. Use only what\n"
    "  the Verified team context provides.\n"
    "- CAREER-STAGE PRECISION: do not call any player a 'rookie', 'first-year',\n"
    "  'four games into their career', or similar UNLESS the Verified player\n"
    "  tenure section explicitly says so. When in doubt, omit career-stage framing.\n"
    "- ROSTER DISCIPLINE: reference only players named in the Verified roster above.\n"
    "- HEDGE EARLY-SEASON CLAIMS: for any 'this team is X' framing in the first ~10\n"
    "  games of a season, hedge openly. Acknowledge sample-size limits."
)


def build_prompt(team, article_type):
    """Compose the Claude prompt for the given team + article_type."""
    persona_name = team.get("persona") or "an NSMT writer"
    persona_voice = team.get("voice") or "professional and engaging"
    kb = load_team_kb(team)
    kb_block = kb_context_block(kb)

    if article_type == "season_so_far":
        current_record_summary = _record_summary_hint(kb)
        return (
            f"You are {persona_name}, an AI sports writer for NSMT (Nova Sports Media\n"
            f"Team), the DMV's premier independent sports media outlet covering Washington\n"
            f"DC, Maryland, and Virginia. NSMT is transparent that you are an AI — readers\n"
            f"know your byline is AI-authored. Your voice: {persona_voice}.\n"
            f"{kb_block}\n"
            f"Write a 700-900 word season-so-far feature on the {team['name']}. This is the\n"
            f"first article you've published this season — it's a foundation piece. Future\n"
            f"recaps will build on it.\n\n"
            f"Cover:\n"
            f"- Where the team stands right now ({current_record_summary})\n"
            f"- Key storylines from the season so far — what's working, what isn't\n"
            f"- Standout players and performances\n"
            f"- What to watch in the coming weeks\n"
            f"- Honest assessment, in your voice\n\n"
            f"Guidelines:\n"
            f"- Stay in your voice ({persona_voice}) but keep it professional, written for\n"
            f"  DC/MD/VA sports fans.\n"
            f"- Use specific players, coaches, and recent game results from the verified\n"
            f"  team context above. Do NOT fabricate stats, dates, or quotes.\n"
            f"- Do NOT refer to yourself in first person or call attention to being AI in\n"
            f"  the article body — the byline handles disclosure.\n"
            f"- Format: plain paragraphs only. No headers, no bullet points.\n\n"
            f"Editorial guardrails (HARD requirements):\n"
            f"{_BASELINE_GUARDRAILS}\n\n"
            f"End with a single line starting with EXCERPT: a one-sentence teaser (max 160 characters)."
        )

    if article_type == "offseason_outlook":
        return (
            f"You are {persona_name}, an AI sports writer for NSMT (Nova Sports Media\n"
            f"Team), the DMV's premier independent sports media outlet covering Washington\n"
            f"DC, Maryland, and Virginia. NSMT is transparent that you are an AI — readers\n"
            f"know your byline is AI-authored. Your voice: {persona_voice}.\n"
            f"{kb_block}\n"
            f"Write a 700-900 word season recap + offseason outlook on the {team['name']}.\n"
            f"This is NSMT's first article on this team — it establishes that we're\n"
            f"covering them and orients readers on the state of the program.\n\n"
            f"Cover:\n"
            f"- How the just-completed season went (final record, key moments,\n"
            f"  high/low points)\n"
            f"- Coaching, roster, or front-office changes since the season ended\n"
            f"- What's known about the upcoming season — schedule, roster expectations,\n"
            f"  storylines\n"
            f"- Honest assessment in your voice\n\n"
            f"Guidelines:\n"
            f"- Stay in your voice ({persona_voice}) but keep it professional, written for\n"
            f"  DC/MD/VA sports fans.\n"
            f"- Use specific players, coaches, and recent results from the verified team\n"
            f"  context above. Do NOT fabricate stats, dates, or quotes.\n"
            f"- Acknowledge uncertainty where the KB doesn't have data (e.g., 2026-27\n"
            f"  schedule). Don't speculate beyond what's verified.\n"
            f"- Do NOT refer to yourself in first person or call attention to being AI in\n"
            f"  the article body.\n"
            f"- Format: plain paragraphs only. No headers, no bullet points.\n\n"
            f"Editorial guardrails (HARD requirements):\n"
            f"{_BASELINE_GUARDRAILS}\n\n"
            f"End with a single line starting with EXCERPT: a one-sentence teaser (max 160 characters)."
        )

    raise ValueError(f"Unknown article_type: {article_type}")


# ── Claude call ───────────────────────────────────────────────────────────────

def generate_baseline(team, article_type):
    """Call Claude. Returns the article text (string) or None on failure."""
    if not ANTHROPIC_API_KEY:
        print("  ERROR: ANTHROPIC_API_KEY not set.")
        return None

    prompt = build_prompt(team, article_type)

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 2048,  # 700-900 words ≈ ~1400 tokens, plus excerpt
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]
    except Exception as e:
        print(f"  Claude API error: {e}")
        return None


# ── Title / slug / metadata ───────────────────────────────────────────────────

def build_title(team, article_type):
    if article_type == "season_so_far":
        return f"{team['name']} 2026 Season So Far — {persona_first_name(team)}'s Read"
    if article_type == "offseason_outlook":
        return f"{team['name']}: Season Recap & What's Next"
    raise ValueError(f"Unknown article_type: {article_type}")


def build_slug(team, target_date):
    return f"{team_slug(team)}-baseline-{target_date.isoformat()}"


def split_body_excerpt(article_text):
    """Return (body, excerpt). Tolerant of missing EXCERPT line."""
    body = article_text
    excerpt = ""
    if "EXCERPT:" in article_text:
        parts = article_text.rsplit("EXCERPT:", 1)
        body = parts[0].strip()
        excerpt = parts[1].strip()
    return body, excerpt


def paragraphs_to_html(body):
    """Wrap paragraphs in <p> tags for the admin rich-text editor."""
    return "".join(f"<p>{p.strip()}</p>" for p in body.split("\n\n") if p.strip())


def word_count(body):
    return len(body.split())


# ── Admin save (baseline-flavored) ────────────────────────────────────────────

def save_baseline_to_nsmt(title, slug, html_body, team, token):
    """Save a baseline article as an inactive draft. Returns blogId or None."""
    if not token:
        return None
    category_id = CATEGORY_IDS.get(team.get("category", "pro"), CATEGORY_IDS["pro"])
    try:
        resp = requests.post(
            f"{NSMT_API}/admin/blogs",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "title":        title,
                "slug":         slug,
                "category_id":  category_id,
                "author":       build_byline(team),
                "author_image": "blogs/authors/1748435759641.jpg",
                "description":  html_body,
                "content":      "",
                "image":        "",
                "is_active":    False,
                "is_popular":   True,
            },
            timeout=20,
        )
        resp.raise_for_status()
        blog_id = resp.json().get("blogId", "")
        return blog_id or "ok"
    except Exception as e:
        print(f"  NSMT admin save failed: {e}")
        return None


# ── Local fallback draft ──────────────────────────────────────────────────────

def save_local_baseline_draft(title, body, team, article_type, target_date):
    """Fallback: write the article to drafts/ as Markdown."""
    os.makedirs("drafts", exist_ok=True)
    filename = (
        f"drafts/{target_date.isoformat()}-{team_slug(team) or slugify(team['name'])}"
        f"-baseline.md"
    )
    with open(filename, "w") as f:
        f.write(f"# {title}\n\n")
        f.write(f"**Team:** {team['name']}  \n")
        f.write(f"**League:** {team['league']}  \n")
        f.write(f"**Article type:** {article_type}  \n")
        f.write(f"**Byline:** {build_byline(team)}  \n")
        f.write(f"**Date:** {target_date.isoformat()}  \n\n")
        f.write("---\n\n")
        f.write(body)
    print(f"  Saved local draft: {filename}")


# ── Discord notification (baseline-flavored) ──────────────────────────────────

def post_baseline_to_discord(title, excerpt, team, article_type, target_date):
    """Best-effort baseline notification. Never raises."""
    if not DISCORD_PROXY_URL or not DISCORD_PROXY_SECRET:
        print("  Discord notification skipped — DISCORD_PROXY_URL / DISCORD_PROXY_SECRET not set.")
        return False

    safe_excerpt = (excerpt or "").strip() or "(no excerpt provided)"
    if len(safe_excerpt) > 400:
        safe_excerpt = safe_excerpt[:399] + "…"

    channel_target = team.get("channel_target") or DISCORD_TARGET
    byline = build_byline(team)

    type_label = {
        "season_so_far":     "Season-so-far",
        "offseason_outlook": "Recap + outlook",
    }.get(article_type, article_type)

    embed = {
        "title":       f"📰 Season Baseline — {team['name']}",
        "description": safe_excerpt,
        "color":       NSMT_BLUE,
        "fields": [
            {"name": "📄 Type",    "value": type_label,                                "inline": True},
            {"name": "🏟️ League",  "value": team["league"],                            "inline": True},
            {"name": "✍️ Byline",  "value": byline,                                    "inline": False},
            {"name": "📌 Title",   "value": title,                                     "inline": False},
            {"name": "✏️ Review",  "value": f"[Open in admin]({ADMIN_REVIEW_URL})",    "inline": False},
        ],
        "footer":    {"text": f"{team['league']} · status: draft (is_active=0) in admin"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    thread_name = f"Baseline — {team['name']} ({target_date.isoformat()})"
    if len(thread_name) > 100:
        thread_name = thread_name[:99] + "…"

    payload = {
        "thread_name": thread_name,
        "embeds":      [embed],
    }

    try:
        resp = requests.post(
            DISCORD_PROXY_URL,
            headers={
                "X-NSMT-Auth":   DISCORD_PROXY_SECRET,
                "X-NSMT-Target": channel_target,
                "Content-Type":  "application/json",
            },
            json=payload,
            timeout=15,
        )
        if resp.status_code < 300:
            print(f"  ✓ Discord notification posted to target='{channel_target}' (status {resp.status_code})")
            return True
        print(f"  ✗ Discord notification failed (status {resp.status_code}): {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"  ✗ Discord notification error: {e}")
        return False


# ── Per-team execution ────────────────────────────────────────────────────────

# Teams whose LEAGUE is still in season per LEAGUE_SEASONS, but who are
# personally eliminated and should be treated as off-season for the baseline.
# As of 2026-05-22: Wizards missed the play-in / Capitals lost in round 1.
FORCE_OFFSEASON_SLUGS = {"wizards", "capitals"}


def article_type_for(team, target_date):
    slug = (team_slug(team) or "").lower()
    if slug in FORCE_OFFSEASON_SLUGS:
        return "offseason_outlook"
    return "season_so_far" if in_season(team, target_date) else "offseason_outlook"


def process_team(team, target_date, token, args, idx, total):
    article_type = article_type_for(team, target_date)
    persona = team.get("persona") or "Unknown"
    slug = team_slug(team) or slugify(team["name"])

    header = (
        f"\n[{idx}/{total}] {team['name']} ({persona}) — {article_type}  "
        f"[slug={slug}]"
    )
    print(header)

    if args.dry_run:
        title = build_title(team, article_type)
        article_slug = build_slug(team, target_date)
        kb = load_team_kb(team)
        kb_status = "KB present" if kb else "KB MISSING"
        print(f"  [DRY RUN] Would call Claude with article_type={article_type}")
        print(f"  [DRY RUN] {kb_status}")
        print(f"  [DRY RUN] Title:  {title}")
        print(f"  [DRY RUN] Slug:   {article_slug}")
        print(f"  [DRY RUN] Byline: {build_byline(team)}")
        if not args.no_admin:
            print(f"  [DRY RUN] Would save draft to admin (is_active=False)")
        else:
            print(f"  [DRY RUN] Would SKIP admin save (--no-admin)")
        if not args.no_discord:
            print(f"  [DRY RUN] Would post Discord notification to target='{team.get('channel_target') or DISCORD_TARGET}'")
        else:
            print(f"  [DRY RUN] Would SKIP Discord (--no-discord)")
        return True

    # Real run from here on.
    article_text = generate_baseline(team, article_type)
    if not article_text:
        print(f"  ✗ Article generation failed, skipping.")
        return False

    body, excerpt = split_body_excerpt(article_text)
    wc = word_count(body)
    print(f"  ✓ Generated {wc} words via Claude")

    html_body = paragraphs_to_html(body)
    title = build_title(team, article_type)
    article_slug = build_slug(team, target_date)

    admin_ok = False
    if args.no_admin:
        print(f"  ↷ Admin save skipped (--no-admin)")
    else:
        blog_id = save_baseline_to_nsmt(title, article_slug, html_body, team, token)
        if blog_id:
            print(f"  ✓ Saved draft to admin: BLOG#{blog_id}")
            admin_ok = True
        else:
            print(f"  ✗ Admin save failed — writing local fallback")
            save_local_baseline_draft(title, body, team, article_type, target_date)

    if args.no_discord:
        print(f"  ↷ Discord notification skipped (--no-discord)")
    else:
        # Always best-effort, never blocks
        try:
            post_baseline_to_discord(title, excerpt, team, article_type, target_date)
        except Exception as e:
            print(f"  ✗ Discord notification error: {e}")

    # Always also save a local copy on real runs for audit / no-admin mode
    if args.no_admin or not admin_ok:
        # already saved in failure branch; only save here if no-admin
        if args.no_admin:
            save_local_baseline_draft(title, body, team, article_type, target_date)

    return True


# ── CLI ───────────────────────────────────────────────────────────────────────

def resolve_teams(args):
    """Return the ordered list of teams to process based on CLI flags."""
    teams = list(ALL_TEAMS)

    if args.team:
        wanted = args.team.strip().lower()
        teams = [t for t in teams if (team_slug(t) or "").lower() == wanted]
        if not teams:
            print(f"ERROR: no team matched slug '{args.team}'.")
            print("Known slugs: " + ", ".join(sorted({team_slug(t) for t in ALL_TEAMS if team_slug(t)})))
            sys.exit(2)

    if args.limit is not None:
        teams = teams[: args.limit]

    return teams


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Generate baseline (foundation) articles for each NSMT beat."
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Plan only — no Claude calls, no admin writes, no Discord.")
    p.add_argument("--team", type=str, default=None,
                   help="Only process the team with this KB slug (e.g. commanders).")
    p.add_argument("--limit", type=int, default=None,
                   help="Process only the first N teams.")
    p.add_argument("--no-discord", action="store_true",
                   help="Skip Discord notification (admin save only).")
    p.add_argument("--no-admin", action="store_true",
                   help="Skip admin save (Discord + local draft only).")
    p.add_argument("--date", type=str, default=None,
                   help="Override 'today' (YYYY-MM-DD). Affects in_season() check and slug date.")
    p.add_argument("--sleep", type=float, default=2.0,
                   help="Seconds to sleep between Claude calls (default 2.0).")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"ERROR: --date must be YYYY-MM-DD, got '{args.date}'.")
            sys.exit(2)
    else:
        target_date = date.today()

    teams = resolve_teams(args)

    print(f"\nNSMT Baseline Article Generator — {target_date.isoformat()}")
    print("=" * 50)

    # Plan summary (uses article_type_for so Wizards/Capitals show as offseason)
    in_count  = sum(1 for t in teams if article_type_for(t, target_date) == "season_so_far")
    off_count = len(teams) - in_count
    print(f"Teams to process: {len(teams)}  ({in_count} in-season → season_so_far, "
          f"{off_count} off-season → offseason_outlook)")
    if args.dry_run:
        print("Mode: DRY RUN — no API calls, no admin writes, no Discord.")
    else:
        print("Mode: LIVE — will call Claude, save drafts, and post Discord notifications.")
        if args.no_admin:
            print("  --no-admin: admin save will be skipped (local Markdown fallback used).")
        if args.no_discord:
            print("  --no-discord: Discord notifications will be skipped.")

    # Auth (skip in dry-run and in --no-admin)
    token = None
    if not args.dry_run and not args.no_admin:
        token = get_nsmt_token()
        if token:
            print("Authenticated with thensmt.com ✓")
        else:
            print("WARN: not authenticated — admin saves will fail; local drafts will be used.")

    successes = 0
    total = len(teams)
    for idx, team in enumerate(teams, start=1):
        ok = process_team(team, target_date, token, args, idx, total)
        if ok:
            successes += 1
        # Rate-limit polite delay between Claude calls (skip in dry-run / after last)
        if not args.dry_run and idx < total:
            time.sleep(args.sleep)

    print(f"\nDone. {successes}/{total} baseline articles drafted.")
    if not args.dry_run and not args.no_admin:
        print(f"Review at {ADMIN_REVIEW_URL}")


if __name__ == "__main__":
    main()
