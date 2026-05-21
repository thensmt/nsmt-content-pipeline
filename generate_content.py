"""
NSMT Content Pipeline — Sports Article Generator
Fetches yesterday's game results for DC/MD/VA teams,
generates article drafts via Claude, and saves them to thensmt.com admin portal.

Required environment variables:
  ANTHROPIC_API_KEY     — Claude API key
  NSMT_USERNAME         — admin.thensmt.com login email
  NSMT_PASSWORD         — admin.thensmt.com login password

Optional (enables Discord notifications in #recap-pipeline):
  DISCORD_PROXY_URL     — Cloudflare Worker proxy URL
  DISCORD_PROXY_SECRET  — shared secret matching the worker's SHARED_SECRET
"""

import requests
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

# ── Credentials (set as environment variables) ────────────────────────────────
ANTHROPIC_API_KEY    = os.environ.get("ANTHROPIC_API_KEY")
NSMT_USERNAME        = os.environ.get("NSMT_USERNAME")
NSMT_PASSWORD        = os.environ.get("NSMT_PASSWORD")
DISCORD_PROXY_URL    = os.environ.get("DISCORD_PROXY_URL")
DISCORD_PROXY_SECRET = os.environ.get("DISCORD_PROXY_SECRET")
DISCORD_TARGET       = "RECAPS"
ADMIN_REVIEW_URL     = "https://admin.thensmt.com/#/blogs"
NSMT_BLUE            = 0x0E80FC

# ── NSMT Admin API ─────────────────────────────────────────────────────────────
NSMT_API          = "https://rjl5qaqz7k.execute-api.us-east-1.amazonaws.com/prod"
COGNITO_CLIENT_ID = "2hcr1d2lgo4rpnet7ept0el34j"
COGNITO_URL       = "https://cognito-idp.us-east-1.amazonaws.com/"

# Category IDs on thensmt.com admin
CATEGORY_IDS = {
    "college":      10,
    "pro":          19,  # "Newest" — update once a dedicated pro category is created
    "high_school":  16,
}

# ── DC/MD/VA Teams to track ───────────────────────────────────────────────────
#
# Each team has:
#   persona         — the AI writer's byline name. Always rendered with the
#                     🤖 badge + ", AI Sports Writer" suffix downstream.
#   voice           — one-line voice modifier injected into the Claude prompt.
#                     Keeps baseline tone but flavors per beat.
#   channel_target  — Cloudflare Worker target name → DISCORD_WEBHOOK_URL_<X>.
#                     Default "RECAPS" routes to the shared #recap-pipeline.
#                     When you set up a dedicated channel for a team, change
#                     this AND add the matching worker secret.

TEAMS = [
    # NFL
    {"name": "Washington Commanders", "league": "NFL",      "espn_id": "28",  "sport": "football",    "league_slug": "nfl",                     "category": "pro",
     "persona": "Maxwell Tucker",  "voice": "blunt, X's-and-O's focused, sounds like a longtime NFL beat writer",
     "channel_target": "RECAPS"},
    # NBA
    {"name": "Washington Wizards",    "league": "NBA",      "espn_id": "27",  "sport": "basketball",  "league_slug": "nba",                     "category": "pro",
     "persona": "Casper Wexler",   "voice": "modern, analytics-first, pace-and-space NBA tone",
     "channel_target": "RECAPS"},
    # NHL
    {"name": "Washington Capitals",   "league": "NHL",      "espn_id": "15",  "sport": "hockey",      "league_slug": "nhl",                     "category": "pro",
     "persona": "Ada Frost",       "voice": "tactical, hockey-specific terminology, no-fluff rink-side voice",
     "channel_target": "RECAPS"},
    # MLB
    {"name": "Washington Nationals",  "league": "MLB",      "espn_id": "21",  "sport": "baseball",    "league_slug": "mlb",                     "category": "pro",
     "persona": "Bayes Cooper",    "voice": "stats-curious, contextualizes performances with historical baseball perspective",
     "channel_target": "RECAPS"},
    # WNBA
    {"name": "Washington Mystics",    "league": "WNBA",     "espn_id": "14",  "sport": "basketball",  "league_slug": "wnba",                    "category": "pro",
     "persona": "Sibyl Avery",     "voice": "insightful, draws connections between plays and player tendencies",
     "channel_target": "RECAPS"},
    # NWSL
    {"name": "Washington Spirit",     "league": "NWSL",     "espn_id": "WAS", "sport": "soccer",      "league_slug": "usa.nwsl",                "category": "pro",
     "persona": "Wren Holloway",   "voice": "tactical, internationalist, women's-soccer-savvy",
     "channel_target": "RECAPS"},
    # MLS
    {"name": "DC United",             "league": "MLS",      "espn_id": "DC",  "sport": "soccer",      "league_slug": "usa.1",                   "category": "pro",
     "persona": "Beckett Calloway","voice": "cosmopolitan, MLS-savvy, soccer-purist sensibility",
     "channel_target": "RECAPS"},
    # NBA G-League
    {"name": "Capital City Go-Go",    "league": "G-League", "espn_id": "CCG", "sport": "basketball",  "league_slug": "nba-g-league",            "category": "pro",
     "persona": "Chuck Harrington","voice": "hometown DC voice, prospect-focused, hopeful G-League energy",
     "channel_target": "RECAPS"},
]

COLLEGE_TEAMS = [
    {"name": "Maryland Terrapins",     "league": "College Basketball",         "espn_id": "120",  "sport": "basketball", "league_slug": "mens-college-basketball",   "category": "college",
     "persona": "Terry Lane",      "voice": "hometown Maryland pride, knows the Big Ten landscape",
     "channel_target": "RECAPS"},
    {"name": "Virginia Cavaliers",     "league": "College Basketball",         "espn_id": "258",  "sport": "basketball", "league_slug": "mens-college-basketball",   "category": "college",
     "persona": "Cav Mitchell",    "voice": "refined, slow-burn analysis, ACC tradition",
     "channel_target": "RECAPS"},
    {"name": "Virginia Tech Hokies",   "league": "College Basketball",         "espn_id": "259",  "sport": "basketball", "league_slug": "mens-college-basketball",   "category": "college",
     "persona": "Hayes Bremner",   "voice": "blue-collar, scrappy underdog energy, Lane Stadium pride",
     "channel_target": "RECAPS"},
    {"name": "Georgetown Hoyas",       "league": "College Basketball",         "espn_id": "46",   "sport": "basketball", "league_slug": "mens-college-basketball",   "category": "college",
     "persona": "Vance Hoya",      "voice": "prestige tone, Big East tradition, Hoya Saxa",
     "channel_target": "RECAPS"},
    {"name": "George Mason Patriots",  "league": "College Basketball",         "espn_id": "2244", "sport": "basketball", "league_slug": "mens-college-basketball",   "category": "college",
     "persona": "Mason Adams",     "voice": "scrappy mid-major, history-conscious patriot energy",
     "channel_target": "RECAPS"},
    {"name": "George Mason Patriots",  "league": "Women's College Basketball", "espn_id": "2244", "sport": "basketball", "league_slug": "womens-college-basketball", "category": "college",
     "persona": "Mason Adams",     "voice": "scrappy mid-major, history-conscious patriot energy",
     "channel_target": "RECAPS"},
    {"name": "Mary Washington Eagles", "league": "College Basketball (D3)",    "espn_id": "2942", "sport": "basketball", "league_slug": "mens-college-basketball",   "category": "college",
     "persona": "Eagle Reed",      "voice": "passionate D3 small-school enthusiast",
     "channel_target": "RECAPS"},
]

ALL_TEAMS = TEAMS + COLLEGE_TEAMS


def build_byline(team):
    """Render the persona name as a byline with the AI badge."""
    persona = team.get("persona") or "NSMT Staff"
    return f"🤖 {persona}, AI Sports Writer"


# ── ESPN API helpers ───────────────────────────────────────────────────────────

def get_espn_scores(sport, league_slug, target_date):
    """Fetch scores from ESPN for a given sport/league on a given date."""
    date_str = target_date.strftime("%Y%m%d")
    url = (
        f"https://site.api.espn.com/apis/site/v2/sports"
        f"/{sport}/{league_slug}/scoreboard?dates={date_str}"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json().get("events", [])
    except Exception as e:
        print(f"  ESPN fetch failed for {league_slug}: {e}")
        return []


def find_team_game(events, team_name):
    """Search ESPN events for a game involving our team. Returns game dict or None."""
    team_lower = team_name.lower()
    for event in events:
        competitors = event.get("competitions", [{}])[0].get("competitors", [])
        for comp in competitors:
            if team_lower in comp.get("team", {}).get("displayName", "").lower():
                return event
    return None


def extract_game_summary(event, team_name):
    """Pull key facts from an ESPN event object."""
    comp = event.get("competitions", [{}])[0]
    competitors = comp.get("competitors", [])

    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})

    home_name  = home.get("team", {}).get("displayName", "Home")
    away_name  = away.get("team", {}).get("displayName", "Away")
    home_score = home.get("score", "?")
    away_score = away.get("score", "?")
    status     = event.get("status", {}).get("type", {}).get("description", "")
    venue      = comp.get("venue", {}).get("fullName", "")

    # Top performers
    leaders = []
    for comp_item in competitors:
        for leader_cat in comp_item.get("leaders", []):
            for leader in leader_cat.get("leaders", []):
                stat    = leader_cat.get("shortDisplayName", "")
                athlete = leader.get("athlete", {}).get("displayName", "")
                value   = leader.get("displayValue", "")
                t_name  = comp_item.get("team", {}).get("displayName", "")
                leaders.append(f"{athlete} ({t_name}): {stat} {value}")

    return {
        "matchup": f"{away_name} @ {home_name}",
        "score":   f"{away_name} {away_score}, {home_name} {home_score}",
        "status":  status,
        "venue":   venue,
        "leaders": leaders[:6],
    }


# ── Team knowledge base lookup ────────────────────────────────────────────────

# Map team name (with optional league for ambiguous cases) to the slug used in
# data/teams/{slug}.json. Single source of truth so we don't add a `slug` field
# to every team dict.
_TEAM_SLUG_MAP = {
    ("Washington Commanders",  None):                            "commanders",
    ("Washington Wizards",     None):                            "wizards",
    ("Washington Capitals",    None):                            "capitals",
    ("Washington Nationals",   None):                            "nationals",
    ("Washington Mystics",     None):                            "mystics",
    ("Washington Spirit",      None):                            "spirit",
    ("DC United",              None):                            "dc-united",
    ("Capital City Go-Go",     None):                            "go-go",
    ("Maryland Terrapins",     None):                            "maryland",
    ("Virginia Cavaliers",     None):                            "virginia",
    ("Virginia Tech Hokies",   None):                            "virginia-tech",
    ("Georgetown Hoyas",       None):                            "georgetown",
    ("George Mason Patriots",  "College Basketball"):            "george-mason",
    ("George Mason Patriots",  "Women's College Basketball"):    "george-mason-women",
    ("Mary Washington Eagles", None):                            "mary-washington",
}


def team_slug(team):
    """Resolve the KB slug for a team dict (handles GMU men's/women's disambiguation)."""
    name = team.get("name")
    league = team.get("league")
    # Try exact (name, league) match first; fall back to (name, None)
    return _TEAM_SLUG_MAP.get((name, league)) or _TEAM_SLUG_MAP.get((name, None))


def load_team_kb(team):
    """Load the verified knowledge-base JSON for a team. Returns dict or None."""
    slug = team_slug(team)
    if not slug:
        return None
    path = os.path.join(os.path.dirname(__file__), "data", "teams", f"{slug}.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def kb_context_block(kb):
    """Format selected KB fields as a context block for the Claude prompt.

    Deliberately narrow: head coach, current record, conference, rivalries,
    last 3 games. Don't dump the whole roster — wastes tokens and dilutes
    attention. Game-specific data (the actual recap input) comes from ESPN.
    """
    if not kb:
        return ""

    lines = ["Verified team context (use selectively — only if it adds color or accuracy):"]

    coach = ((kb.get("head_coach") or {}).get("name"))
    if coach:
        lines.append(f"- Head coach: {coach}")

    record = kb.get("current_record")
    if record:
        lines.append(f"- Current record: {record}")

    conf = kb.get("conference")
    div = kb.get("division")
    if conf or div:
        lines.append(f"- Conference/Division: {' / '.join(filter(None, [conf, div]))}")

    rivalries = kb.get("rivalries") or []
    if rivalries:
        # rivalries may be a list of strings OR list of dicts (DC United format)
        rival_names = []
        for r in rivalries[:4]:
            if isinstance(r, str):
                rival_names.append(r)
            elif isinstance(r, dict):
                rival_names.append(r.get("opponent") or "")
        rival_names = [n for n in rival_names if n]
        if rival_names:
            lines.append(f"- Notable rivalries: {', '.join(rival_names)}")

    recent = kb.get("recent_games") or []
    if recent:
        recent_lines = []
        for g in recent[:3]:
            date = g.get("date") or "recent"
            opp = g.get("opponent", "?")
            result = g.get("result", "?")
            venue_marker = "vs" if g.get("venue") == "home" else "@"
            recent_lines.append(f"  · {date} {venue_marker} {opp}: {result}")
        lines.append("- Recent form (last 3):\n" + "\n".join(recent_lines))

    return "\n" + "\n".join(lines) + "\n"


# ── Claude API helper ──────────────────────────────────────────────────────────

def generate_article(game_summary, team, article_type="recap"):
    """Call Claude to write a sports article based on game data."""
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set.")
        return None

    persona_name = team.get("persona") or "an NSMT writer"
    persona_voice = team.get("voice") or "professional and engaging"

    kb = load_team_kb(team)
    kb_block = kb_context_block(kb)

    if article_type == "recap":
        prompt = f"""You are {persona_name}, an AI sports writer for NSMT (Nova Sports Media Team), the DMV's premier independent sports media outlet covering Washington DC, Maryland, and Virginia. NSMT is transparent that you are an AI — readers know your byline is AI-authored. Your voice: {persona_voice}.
{kb_block}
Write a professional, engaging game recap article (400-550 words) for the following game:

Team: {team['name']}
League: {team['league']}
Matchup: {game_summary['matchup']}
Final Score: {game_summary['score']}
Venue: {game_summary['venue']}
Top Performers: {', '.join(game_summary['leaders']) if game_summary['leaders'] else 'Not available'}

Guidelines:
- Open with a strong lede that captures the result
- Highlight key moments and turning points
- Mention standout individual performances
- Add context about standings or season implications
- Close with a forward-looking line about the team's next challenge
- Stay in your voice ({persona_voice}) but keep it professional, written for DC/MD/VA sports fans
- Do NOT fabricate specific play-by-play details not given above
- Do NOT refer to yourself in first person or call attention to being AI in the article body — the byline handles disclosure
- Format: plain paragraphs only, no headers or bullet points

Also provide at the very end, on a new line starting with EXCERPT: a one-sentence teaser (max 160 characters) for the article preview."""

    elif article_type == "preview":
        prompt = f"""You are {persona_name}, an AI sports writer for NSMT (Nova Sports Media Team), the DMV's premier independent sports media outlet. Your voice: {persona_voice}.
{kb_block}
Write a professional game preview article (350-450 words) for the upcoming game:

Team: {team['name']}
League: {team['league']}
Matchup: {game_summary['matchup']}
Venue: {game_summary['venue']}

Guidelines:
- Preview the matchup and what's at stake
- Discuss key players to watch on both sides
- Mention recent form or storylines where relevant
- Stay in your voice but keep it professional, for DC/MD/VA fans
- Do NOT refer to yourself in first person or call attention to being AI in the body
- Format: plain paragraphs only, no headers or bullet points

Also provide at the very end, on a new line starting with EXCERPT: a one-sentence teaser (max 160 characters)."""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-opus-4-6",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"]
        return content
    except Exception as e:
        print(f"  Claude API error: {e}")
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def get_nsmt_token():
    """Authenticate with Cognito and return a fresh JWT."""
    if not NSMT_USERNAME or not NSMT_PASSWORD:
        print("  Skipping NSMT admin — NSMT_USERNAME or NSMT_PASSWORD not set.")
        return None
    try:
        resp = requests.post(
            COGNITO_URL,
            headers={
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            },
            json={
                "AuthFlow": "USER_PASSWORD_AUTH",
                "ClientId": COGNITO_CLIENT_ID,
                "AuthParameters": {"USERNAME": NSMT_USERNAME, "PASSWORD": NSMT_PASSWORD},
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["AuthenticationResult"]["IdToken"]
    except Exception as e:
        print(f"  Cognito auth failed: {e}")
        return None


def save_to_nsmt(title, slug, content, excerpt, team, game_date, token):
    """Save article as an inactive draft to thensmt.com admin portal."""
    if not token:
        return False
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
                "description":  content,
                "content":      "",
                "image":        "",
                "is_active":    False,
                "is_popular":   True,
            },
            timeout=15,
        )
        resp.raise_for_status()
        blog_id = resp.json().get("blogId", "")
        print(f"  Saved draft to thensmt.com: {blog_id}")
        return True
    except Exception as e:
        print(f"  NSMT admin save failed: {e}")
        return False


def post_recap_to_discord(title, excerpt, team, summary, game_date):
    """Best-effort notification to Discord via the Cloudflare Worker proxy.

    Routes to the team's own channel if `team["channel_target"]` matches a
    configured `DISCORD_WEBHOOK_URL_<X>` secret on the worker. Otherwise the
    worker falls back to the default webhook (currently #recap-pipeline via
    the RECAPS target, which is the default for all teams until you opt them
    into per-team channels).

    Never raises — Discord failure must not block admin saves.
    """
    if not DISCORD_PROXY_URL or not DISCORD_PROXY_SECRET:
        print("  Discord notification skipped — DISCORD_PROXY_URL / DISCORD_PROXY_SECRET not set.")
        return False

    safe_excerpt = (excerpt or "").strip() or "(no excerpt provided)"
    if len(safe_excerpt) > 400:
        safe_excerpt = safe_excerpt[:399] + "…"

    channel_target = team.get("channel_target") or DISCORD_TARGET
    byline = build_byline(team)

    embed = {
        "title":       f"📝 New Recap Draft — {team['name']}",
        "description": safe_excerpt,
        "color":       NSMT_BLUE,
        "fields": [
            {"name": "✍️ Byline",  "value": byline,                                    "inline": False},
            {"name": "🏆 Game",    "value": summary.get("score", "Score unavailable"), "inline": False},
            {"name": "📅 Date",    "value": game_date.isoformat(),                      "inline": True},
            {"name": "🏟️ Venue",  "value": summary.get("venue") or "Unknown",         "inline": True},
            {"name": "✏️ Review",  "value": f"[Open in admin]({ADMIN_REVIEW_URL})",    "inline": False},
        ],
        "footer":    {"text": f"{team['league']} · status: draft (is_active=0) in admin"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    thread_name = f"{team['name']} — {game_date.isoformat()}"
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


def save_local_draft(title, body, team, game_date):
    """Fallback: save article as a local Markdown file."""
    os.makedirs("drafts", exist_ok=True)
    filename = f"drafts/{game_date.isoformat()}-{slugify(team['name'])}.md"
    with open(filename, "w") as f:
        f.write(f"# {title}\n\n")
        f.write(f"**Team:** {team['name']}  \n")
        f.write(f"**League:** {team['league']}  \n")
        f.write(f"**Date:** {game_date.isoformat()}  \n\n")
        f.write("---\n\n")
        f.write(body)
    print(f"  Saved local draft: {filename}")


# ── Main ───────────────────────────────────────────────────────────────────────

def run(target_date=None):
    if target_date is None:
        target_date = date.today() - timedelta(days=1)  # yesterday by default

    print(f"\nNSMT Content Pipeline — {target_date.isoformat()}")
    print("=" * 50)

    # Get a single fresh token for this run
    token = get_nsmt_token()
    if token:
        print("✓ Authenticated with thensmt.com")

    articles_generated = 0
    fetched = {}

    for team in ALL_TEAMS:
        key = (team["sport"], team["league_slug"])
        if key not in fetched:
            print(f"\nFetching {team['league']} scores...")
            fetched[key] = get_espn_scores(team["sport"], team["league_slug"], target_date)

        events = fetched[key]
        game = find_team_game(events, team["name"])

        if not game:
            print(f"  {team['name']}: no game found on {target_date.isoformat()}")
            continue

        print(f"  {team['name']}: game found — generating article...")
        summary = extract_game_summary(game, team["name"])
        article_text = generate_article(summary, team, article_type="recap")

        if not article_text:
            print(f"  {team['name']}: article generation failed, skipping.")
            continue

        # Split body and excerpt
        body = article_text
        excerpt = ""
        if "EXCERPT:" in article_text:
            parts = article_text.rsplit("EXCERPT:", 1)
            body    = parts[0].strip()
            excerpt = parts[1].strip()

        # Wrap paragraphs in HTML <p> tags for the rich text editor
        body = "".join(f"<p>{p.strip()}</p>" for p in body.split("\n\n") if p.strip())

        title = f"{summary['score']} | {team['name']} Recap"
        slug  = slugify(f"{team['name']}-recap-{target_date.isoformat()}")

        saved = save_to_nsmt(title, slug, body, excerpt, team, target_date, token)
        if saved:
            post_recap_to_discord(title, excerpt, team, summary, target_date)
        else:
            save_local_draft(title, body, team, target_date)

        articles_generated += 1

    print(f"\nDone. {articles_generated} article(s) generated for {target_date.isoformat()}.")
    print("Review drafts at: https://admin.thensmt.com/#/blogs")


if __name__ == "__main__":
    # Optionally pass a date: python generate_content.py 2026-03-13
    if len(sys.argv) > 1:
        from datetime import datetime
        target = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    else:
        target = None
    run(target)
