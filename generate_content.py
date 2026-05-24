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
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from style_guide import NO_META_COMMENTARY, AI_TELLS_AVOIDANCE

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

# ── League season windows ────────────────────────────────────────────────────
#
# (start_month, end_month) per league name. Months are inclusive. If start > end
# the season wraps the calendar year (e.g., NBA: Oct → Jun). Windows are
# intentionally generous to include preseason and full playoffs.
#
# Teams whose league is out-of-season on the target_date are skipped before any
# ESPN fetch — saves API calls, keeps logs scannable, and avoids spurious
# errors from ESPN endpoints that change between seasons.

LEAGUE_SEASONS = {
    "NFL":                          (8, 2),    # preseason Aug → Super Bowl Feb
    "NBA":                          (10, 6),   # regular season Oct → Finals Jun
    "NHL":                          (10, 6),   # regular season Oct → Cup Final Jun
    "MLB":                          (3, 11),   # spring Mar → World Series Oct/Nov
    "WNBA":                         (5, 10),   # May → Finals Oct
    "NWSL":                         (3, 11),   # Mar → Championship Nov
    "MLS":                          (2, 12),   # Feb → MLS Cup Dec
    "UFL":                          (3, 6),    # spring pro football Mar → Championship Jun
    "G-League":                     (11, 4),   # Nov → playoffs Apr
    "College Basketball":           (11, 4),   # Nov → NCAA tourney Apr
    "Women's College Basketball":   (11, 4),
    "College Basketball (D3)":      (11, 4),
}


def in_season(team, when):
    """Return True if `team` is in season on the date `when`. If the league
    has no window configured, returns True (safe default)."""
    window = LEAGUE_SEASONS.get(team.get("league"))
    if not window:
        return True
    start, end = window
    m = when.month
    if start <= end:
        return start <= m <= end
    # wraps year boundary, e.g. NBA Oct-Jun
    return m >= start or m <= end

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
    {"name": "Washington Capitals",   "league": "NHL",      "espn_id": "23",  "sport": "hockey",      "league_slug": "nhl",                     "category": "pro",
     "persona": "Ada Frost",       "voice": "tactical, hockey-specific terminology, no-fluff rink-side voice",
     "channel_target": "RECAPS"},
    # MLB
    {"name": "Washington Nationals",  "league": "MLB",      "espn_id": "20",  "sport": "baseball",    "league_slug": "mlb",                     "category": "pro",
     "persona": "Marcus Bell",     "voice": "stats-curious, contextualizes performances with historical baseball perspective",
     "channel_target": "RECAPS"},
    # WNBA
    {"name": "Washington Mystics",    "league": "WNBA",     "espn_id": "16",  "sport": "basketball",  "league_slug": "wnba",                    "category": "pro",
     "persona": "Sibyl Avery",     "voice": "insightful, draws connections between plays and player tendencies",
     "channel_target": "RECAPS"},
    # NWSL
    {"name": "Washington Spirit",     "league": "NWSL",     "espn_id": "15365", "sport": "soccer",    "league_slug": "usa.nwsl",                "category": "pro",
     "persona": "Wren Holloway",   "voice": "tactical, internationalist, women's-soccer-savvy",
     "channel_target": "RECAPS"},
    # MLS
    {"name": "DC United",             "league": "MLS",      "espn_id": "193", "sport": "soccer",      "league_slug": "usa.1",                   "category": "pro",
     "persona": "Beckett Calloway","voice": "cosmopolitan, MLS-savvy, soccer-purist sensibility",
     "channel_target": "RECAPS"},
    # NBA G-League
    {"name": "Capital City Go-Go",    "league": "G-League", "espn_id": "CCG", "sport": "basketball",  "league_slug": "nba-g-league",            "category": "pro",
     "persona": "Chuck Harrington","voice": "hometown DC voice, prospect-focused, hopeful G-League energy",
     "channel_target": "RECAPS"},
    # UFL (spring pro football)
    {"name": "DC Defenders",          "league": "UFL",      "espn_id": "112646", "sport": "football", "league_slug": "ufl",                    "category": "pro",
     "persona": "Vince Kessler",   "voice": "spring-football-savvy, treats UFL as its own legitimate pro league with NFL-prospect-watching energy",
     "channel_target": "DC_DEFENDERS"},
]

COLLEGE_TEAMS = [
    {"name": "Maryland Terrapins",     "league": "College Basketball",         "espn_id": "120",  "sport": "basketball", "league_slug": "mens-college-basketball",   "category": "college",
     "persona": "Terry Lane",      "voice": "hometown Maryland pride, knows the Big Ten landscape",
     "channel_target": "RECAPS"},
    {"name": "Virginia Cavaliers",     "league": "College Basketball",         "espn_id": "258",  "sport": "basketball", "league_slug": "mens-college-basketball",   "category": "college",
     "persona": "Graham Ellis",    "voice": "refined, slow-burn analysis, ACC tradition",
     "channel_target": "RECAPS"},
    {"name": "Virginia Tech Hokies",   "league": "College Basketball",         "espn_id": "259",  "sport": "basketball", "league_slug": "mens-college-basketball",   "category": "college",
     "persona": "Hayes Bremner",   "voice": "blue-collar, scrappy underdog energy, Lane Stadium pride",
     "channel_target": "RECAPS"},
    {"name": "Georgetown Hoyas",       "league": "College Basketball",         "espn_id": "46",   "sport": "basketball", "league_slug": "mens-college-basketball",   "category": "college",
     "persona": "Patrick Keane",   "voice": "prestige tone, Big East tradition, Hoya Saxa",
     "channel_target": "RECAPS"},
    {"name": "George Mason Patriots",  "league": "College Basketball",         "espn_id": "2244", "sport": "basketball", "league_slug": "mens-college-basketball",   "category": "college",
     "persona": "Mason Adams",     "voice": "scrappy mid-major, history-conscious patriot energy",
     "channel_target": "RECAPS"},
    {"name": "George Mason Patriots",  "league": "Women's College Basketball", "espn_id": "2244", "sport": "basketball", "league_slug": "womens-college-basketball", "category": "college",
     "persona": "Mason Adams",     "voice": "scrappy mid-major, history-conscious patriot energy",
     "channel_target": "RECAPS"},
    {"name": "Mary Washington Eagles", "league": "College Basketball (D3)",    "espn_id": "2942", "sport": "basketball", "league_slug": "mens-college-basketball",   "category": "college",
     "persona": "Natalie Park",    "voice": "passionate D3 small-school enthusiast",
     "channel_target": "RECAPS"},
    {"name": "American University Eagles",        "league": "College Basketball",      "espn_id": "44",   "sport": "basketball", "league_slug": "mens-college-basketball",   "category": "college",
     "persona": "Theo Marlin",     "voice": "Patriot League academic-meets-athletic tone, knows the league's quirks and traditions",
     "channel_target": "AMERICAN"},
    {"name": "George Washington Revolutionaries", "league": "College Basketball",      "espn_id": "45",   "sport": "basketball", "league_slug": "mens-college-basketball",   "category": "college",
     "persona": "Henry Voss",      "voice": "refined DC private-school A-10 voice, urban sensibility, distinct from mid-major scrappiness",
     "channel_target": "GEORGE_WASHINGTON"},
    {"name": "Marymount University Saints",       "league": "College Basketball (D3)", "espn_id": None,   "sport": "basketball", "league_slug": "mens-college-basketball",   "category": "college",
     "persona": "Caroline Vega",   "voice": "Atlantic East D-III voice, focused on student-athlete journeys and the Arlington-area community",
     "channel_target": "MARYMOUNT"},
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
    ("DC Defenders",                       None):                "dc-defenders",
    ("American University Eagles",         None):                "american",
    ("Marymount University Saints",        None):                "marymount",
    ("George Washington Revolutionaries",  None):                "george-washington",
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


def load_story_packet(team, target_date):
    """Load the timely story packet JSON for a team on a given date.
    Returns dict or None. Packets live at data/packets/{slug}_{YYYY-MM-DD}.json
    and are produced by the ingestion module (currently Mystics-only)."""
    slug = team_slug(team)
    if not slug or not target_date:
        return None
    path = os.path.join(
        os.path.dirname(__file__), "data", "packets", f"{slug}_{target_date.isoformat()}.json"
    )
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


_TENURE_ORDINALS = {1: "2nd", 2: "3rd", 3: "4th", 4: "5th", 5: "6th", 6: "7th",
                    7: "8th", 8: "9th", 9: "10th"}

# Leagues where draft year ≈ pro debut year, so "current_year - draft_year + 1"
# gives the correct season number for tenure derivation. Drafted players in
# these leagues typically go straight to the pro roster.
#
# DELIBERATELY EXCLUDES:
#   - MLB: drafted players spend 1-5 years in the minors before debut. A 2023
#     draftee might not have made MLB until 2024 or later, so "2026 - 2023 + 1
#     = 4th MLB season" is wrong (it'd be their 3rd or even 2nd).
#   - NHL: same problem. AHL/junior development time between draft and NHL
#     debut.
#   - College leagues: there's no "draft" in the college sense.
#
# For excluded leagues, tenure derivation skips. BIOGRAPHICAL LOCKDOWN in the
# writer prompt is the safety net — the writer must not invent career-stage
# claims that aren't supported by the source.
_TENURE_DRAFT_DIRECT_LEAGUES = {
    "WNBA",
    "NBA",
    "NFL",
    "G-League",
    "UFL",
    "MLS",
    "NWSL",
}


def _derive_player_tenure(notes, current_season, league):
    """Derive explicit career-stage framing (e.g. 'in 2nd WNBA season') from a
    roster note like '2025 No. 4 overall draft pick'. Returns a short string
    or None.

    Only fires for leagues in _TENURE_DRAFT_DIRECT_LEAGUES — for MLB / NHL the
    draft-to-debut gap means draft year is the wrong anchor (see set comment).

    The 2026-05-22 demo eval showed that passing the raw draft-pick note alone
    is NOT enough — the model still framed a 2nd-year player as a rookie.
    Pre-computing the season number here gives the prompt an unambiguous,
    non-derivable fact.
    """
    if not notes or not current_season:
        return None
    if league not in _TENURE_DRAFT_DIRECT_LEAGUES:
        return None
    m = (
        re.search(r"(\d{4})\s+No\.\s+\d+\s+overall\s+draft", notes)
        or re.search(r"drafted\s+(\d{4})", notes, re.IGNORECASE)
        or re.search(r"(\d{4})\s+draft", notes)
    )
    if not m:
        return None
    try:
        draft_year = int(m.group(1))
        current_year = int(str(current_season)[:4])
    except (ValueError, TypeError):
        return None
    diff = current_year - draft_year
    if diff < 0 or diff > 30:
        return None
    league_label = league or "pro"
    if diff == 0:
        return f"{league_label} rookie"
    label = _TENURE_ORDINALS.get(diff, f"{diff + 1}th")
    return f"in {label} {league_label} season"


def _coach_title(coach):
    """Return the title noun for the head coach role. Defaults to 'Head coach'
    so existing KBs that don't set head_coach.title (basketball / hockey /
    football / soccer — where 'Head coach' is correct) keep their current
    rendering. Baseball KBs should set head_coach.title = 'Manager'."""
    if not coach:
        return "Head coach"
    return (coach.get("title") or "Head coach").strip() or "Head coach"


def _derive_coach_tenure(coach, current_season):
    """Derive 'in Nth year as {title}' from coach.tenure_start vs current_season.
    Returns a short string or None. Title comes from coach.title (KB-driven)
    with a 'head coach' default — so baseball KBs that set title='Manager'
    render 'in 1st year as manager'.

    Same motivation as player tenure: prevents the writer from inferring a
    coach's tenure incorrectly."""
    if not coach or not current_season:
        return None
    start = coach.get("tenure_start")
    if not start:
        return None
    try:
        start_year = int(str(start)[:4])
        current_year = int(str(current_season)[:4])
    except (ValueError, TypeError):
        return None
    diff = current_year - start_year
    if diff < 0 or diff > 50:
        return None
    title_lower = _coach_title(coach).lower()
    if diff == 0:
        return f"in 1st year as {title_lower}"
    label = _TENURE_ORDINALS.get(diff, f"{diff + 1}th")
    return f"in {label} year as {title_lower}"


def kb_context_block(kb):
    """Format selected KB fields as a context block for the Claude prompt.

    Renders coach, record, conference, rivalries, recent form, AND — added
    2026-05-22 after the Mystics demo eval — the verified roster plus
    pre-computed player tenure ('in 2nd WNBA season'). The roster gives the
    model a closed-set of names to reference; the tenure block kills the
    rookie-framing hallucination class we saw in the demo.

    Game-specific data (the actual recap input) still comes from ESPN at
    call time and from the story packet (see consume_story_packet).
    """
    if not kb:
        return ""

    team_name = kb.get("team_name") or "the team"
    lines = ["Verified team context (use selectively — only if it adds color or accuracy):"]

    coach_dict = kb.get("head_coach") or {}
    coach = coach_dict.get("name")
    if coach:
        title = _coach_title(coach_dict)
        coach_tenure = _derive_coach_tenure(coach_dict, kb.get("current_season"))
        if coach_tenure:
            lines.append(f"- {title}: {coach} ({coach_tenure})")
        else:
            lines.append(f"- {title}: {coach}")

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

    roster = kb.get("roster") or []
    current_season = kb.get("current_season")
    league = kb.get("league") or ""

    tenured = []
    for p in roster:
        notes = p.get("notes") or ""
        tenure = _derive_player_tenure(notes, current_season, league)
        if tenure:
            tenured.append((p.get("name", ""), tenure, notes))

    if tenured:
        lines.append(
            "- Verified player tenure (these are FACTS, not inferences — "
            "do not contradict them; do not describe these players as rookies "
            "or use 'first-year' / 'N games into their career' framing):"
        )
        for name, tenure, notes in tenured:
            lines.append(f"  · {name} — {tenure} ({notes})")

    if roster:
        lines.append(
            f"- Verified {team_name} roster (reference ONLY these names when "
            "discussing your own team's players; opposing-team names from the "
            "game data are fine):"
        )
        for p in roster:
            nm = p.get("name", "")
            pos = p.get("position") or ""
            num = p.get("number") or ""
            tag_parts = []
            if pos:
                tag_parts.append(pos)
            if num:
                tag_parts.append(f"#{num}")
            tag = f" ({', '.join(tag_parts)})" if tag_parts else ""
            lines.append(f"  · {nm}{tag}")

    # Editorial lessons accumulated from past fact-check / Codex reviews of
    # articles about this team. Each entry is `{date_added, lesson, source}`.
    # The writer should treat these as binding instructions for the current
    # article — they were learned the hard way.
    lessons = kb.get("editorial_lessons") or []
    if lessons:
        lines.append("- Prior-review lessons for this team (apply these — they reflect issues caught by fact-checkers on past articles):")
        for entry in lessons:
            if isinstance(entry, dict):
                text = entry.get("lesson", "")
                if text:
                    lines.append(f"  · {text}")
            elif isinstance(entry, str) and entry.strip():
                lines.append(f"  · {entry.strip()}")

    return "\n" + "\n".join(lines) + "\n"


# ── Story packet (ingestion layer) ───────────────────────────────────────────
#
# Story packets are produced by the ingestion module (see ingestion/) and live
# at data/packets/{slug}_{YYYY-MM-DD}.json. They carry TIMELY enrichment
# (the day's game, top performers, news, injuries, standings, per-player
# boxscores) — distinct from KB files which carry TIMELESS team context.

def _format_boxscore_rows(boxscore):
    """Compact per-player rendering from a TeamBoxscore dict.

    Prefers the new sport-neutral `entries` shape (boxscore.entries — used by
    every team except Mystics). Falls back to the legacy basketball-shaped
    `rows` field for Mystics packets that haven't been migrated.

    Returns a list of strings. When the boxscore has multiple sections (e.g.
    baseball has 'batting' + 'pitching'), section headers are inserted as
    sentinel lines like '[Batting]' so the caller can format them.
    """
    if not boxscore:
        return []
    entries = boxscore.get("entries") or []
    if entries:
        return _format_boxscore_entries(entries)
    # Legacy basketball path for Mystics
    return _format_boxscore_rows_basketball(boxscore.get("rows") or [])


def _format_boxscore_entries(entries):
    """Group sport-neutral entries by section and render each player as a one-
    liner with all their stats. Works for any sport ESPN exposes — basketball
    (one 'players' section), baseball (batting + pitching), hockey (skaters +
    goaltenders), football (per-position groups), soccer (one section)."""
    by_section: dict[str, list[dict]] = {}
    section_order: list[str] = []
    for entry in entries:
        section = (entry.get("section") or "players").lower()
        if section not in by_section:
            by_section[section] = []
            section_order.append(section)
        by_section[section].append(entry)

    out: list[str] = []
    for section in section_order:
        section_label = _SECTION_LABELS.get(section, section.title())
        if len(section_order) > 1:
            out.append(f"[{section_label}]")
        for entry in by_section[section]:
            name = entry.get("player") or "?"
            position = entry.get("position") or ""
            starter = entry.get("starter")
            header_parts = []
            if position:
                header_parts.append(position)
            if starter:
                header_parts.append("starter")
            header = f"{name} ({', '.join(header_parts)})" if header_parts else name

            stats = entry.get("stats") or {}
            stat_chunks = [f"{label} {value}" for label, value in stats.items() if value not in (None, "", "0-0")]
            line = f"{header}: " + " · ".join(stat_chunks) if stat_chunks else header
            out.append(line)
    return out


# Section header rendering. Maps ESPN's `type` / `name` values to display labels.
_SECTION_LABELS = {
    "batting":       "Batting",
    "pitching":      "Pitching",
    "skaters":       "Skaters",
    "goaltenders":   "Goaltenders",
    "passing":       "Passing",
    "rushing":       "Rushing",
    "receiving":     "Receiving",
    "defense":       "Defense",
    "kicking":       "Kicking",
    "punting":       "Punting",
    "kick returns":  "Kick Returns",
    "punt returns":  "Punt Returns",
    "players":       "Players",
}


def _format_boxscore_rows_basketball(rows):
    """Legacy renderer for basketball-shaped `BoxscoreRow` entries (the
    Mystics packet format). Preserved verbatim from the original to avoid
    Mystics regression."""
    out = []
    for row in rows:
        name = row.get("player") or "?"
        position = row.get("position") or ""
        minutes = row.get("minutes")
        header_parts = []
        if position:
            header_parts.append(position)
        if minutes:
            header_parts.append(f"{minutes} min")
        if row.get("starter"):
            header_parts.append("starter")
        if "plus_minus" in row:
            header_parts.append(f"{row['plus_minus']:+d}")
        header = f"{name} ({', '.join(header_parts)})" if header_parts else name

        stat_chunks = []
        if "points" in row:
            stat_chunks.append(f"{row['points']} PTS")
        for shooting_key, label in (("fg", "FG"), ("three_pt", "3P"), ("ft", "FT")):
            val = row.get(shooting_key)
            if val and val != "0-0":
                stat_chunks.append(f"{val} {label}")
        for stat_key, label in (
            ("rebounds", "REB"),
            ("assists", "AST"),
            ("steals", "STL"),
            ("blocks", "BLK"),
            ("turnovers", "TO"),
        ):
            if stat_key in row:
                stat_chunks.append(f"{row[stat_key]} {label}")

        line = f"{header}: " + " · ".join(stat_chunks) if stat_chunks else header
        out.append(line)
    return out


def consume_story_packet(packet):
    """Flatten a story packet dict into a prompt-ready context block.

    Mirrors the shape and conventions of kb_context_block(): returns a single
    string (with leading + trailing newlines) ready for concatenation into
    the Claude user prompt. Empty string when the packet is None or empty.

    Tolerates missing keys and silently skips empty sections. List fields may
    contain strings OR dicts; dict items are best-effort stringified.

    Expected packet shape (per ingestion contract):
        event_type:                  game | news | injury | transaction |
                                     standings_update | off_day
        retrieved_at:                ISO 8601 UTC
        kb_slug:                     pointer to data/teams/{slug}.json
        game_summary:                str or dict
        top_performers:              list[str|dict]
        recent_team_context:         str
        key_players:                 list[str|dict]
        injuries_or_availability:    list[str|dict]
        standings_context:           str
        recent_news_items:           list[dict] with title/url/published_at
        editorial_angle_candidates:  list[str]   — suggestions, not requirements
        confidence_notes:            list[str]   — gaps the writer must NOT fabricate around
        source_links:                list[dict] with source_name/source_url/confidence
    """
    if not packet:
        return ""

    out = [f"Story packet (event_type: {packet.get('event_type', 'unknown')}):"]
    if retrieved := packet.get("retrieved_at"):
        out.append(f"- Retrieved: {retrieved}")

    def _bullets(items):
        lines = []
        for it in items:
            if isinstance(it, str):
                lines.append(f"  · {it}")
            elif isinstance(it, dict):
                # news items: prefer title + url; otherwise compact key:value
                if "title" in it:
                    title = it.get("title", "")
                    url = it.get("url") or it.get("source_url") or ""
                    lines.append(f"  · {title}" + (f" ({url})" if url else ""))
                else:
                    lines.append("  · " + ", ".join(f"{k}: {v}" for k, v in it.items()))
        return lines

    def _section(label, body):
        if not body:
            return
        if isinstance(body, (list, tuple)):
            rows = _bullets(body)
            if not rows:
                return
            out.append(f"- {label}:")
            out.extend(rows)
        elif isinstance(body, dict):
            out.append(f"- {label}:")
            for k, v in body.items():
                out.append(f"  · {k}: {v}")
        else:
            out.append(f"- {label}: {body}")

    _section("Game summary",          packet.get("game_summary"))
    _section("Top performers",        packet.get("top_performers"))

    # Full per-player boxscores from ESPN summary. Added 2026-05-22 to kill
    # stat-line hallucination — the writer prompt instructs the model to use
    # ONLY these numbers (or web-search when they're absent), never to invent.
    box = packet.get("boxscore")
    if box:
        out.append(f"- {box.get('team_name', 'Team')} per-player boxscore (this game — use these numbers verbatim, do not paraphrase or compute deltas):")
        for line in _format_boxscore_rows(box):
            out.append(f"  · {line}")
    opp_box = packet.get("opponent_boxscore")
    if opp_box:
        out.append(f"- {opp_box.get('team_name', 'Opponent')} per-player boxscore (opposing team):")
        for line in _format_boxscore_rows(opp_box):
            out.append(f"  · {line}")

    _section("Recent team context",   packet.get("recent_team_context"))
    _section("Key players",           packet.get("key_players"))
    _section("Injuries/availability", packet.get("injuries_or_availability"))
    _section("Standings context",     packet.get("standings_context"))
    _section("Recent news",           packet.get("recent_news_items"))

    if angles := packet.get("editorial_angle_candidates"):
        out.append("- Editorial angle candidates (pick ONE or synthesize — these are suggestions, not requirements):")
        for a in angles:
            out.append(f"  · {a}")

    if notes := packet.get("confidence_notes"):
        out.append("- Confidence notes — DO NOT FABRICATE around these gaps:")
        if isinstance(notes, list):
            for n in notes:
                out.append(f"  · {n}")
        else:
            out.append(f"  · {notes}")

    if sources := packet.get("source_links"):
        out.append("- Sources cited in this packet:")
        for s in sources:
            if isinstance(s, dict):
                name = s.get("source_name", "?")
                url  = s.get("source_url", "")
                conf = s.get("confidence", "?")
                out.append(f"  · {name} ({url}) — confidence {conf}")
            else:
                out.append(f"  · {s}")

    return "\n" + "\n".join(out) + "\n"


# Shared editorial-guardrails block. Added 2026-05-22 after the Mystics demo
# eval flagged overclaiming, source-mixing, and rookie-framing errors; bio-
# claim lockdown added the same day. Module-level so one-off scripts
# (scripts/demo_citron_feature.py and any future demos) can import + reuse
# without duplicating. KEEP THE SINGLE SOURCE OF TRUTH — do not copy into
# other files. The baselines path uses generate_baselines._BASELINE_GUARDRAILS
# (paraphrased for season-feature framing); changes here should be reflected
# there manually when relevant.
GUARDRAILS = (
    "- ANTI-OVERCLAIM: avoid deterministic causality framings from small "
    "samples (<10 games). Use 'early pattern', 'possible trend', "
    "'worth monitoring' — do not declare team identity from a handful of games.\n"
    "- ANTI-FABRICATION: every stat, date, opponent, score, and player name "
    "must come from the Verified team context, the Story packet, or the game "
    "data below. If a number isn't in those blocks, do not invent one.\n"
    "- NO SOURCE-MIXING: if a number appears in two blocks with different "
    "values, prefer the Story packet; never blend stats from different sources.\n"
    "- CAREER-STAGE PRECISION: do not call any player a 'rookie', 'first-year', "
    "'four games into their career', or similar UNLESS the Verified player "
    "tenure section explicitly says so. When in doubt, omit career-stage framing.\n"
    "- ROSTER DISCIPLINE: reference only players named in the Verified roster "
    "or the game data. Do not invent additional teammates.\n"
    "- BIOGRAPHICAL LOCKDOWN: do not state biographical or contextual facts "
    "about any player or coach (college history, hometown, prior teams, awards, "
    "age, family, draft round/pick beyond what the tenure block provides) "
    "unless that exact fact appears in the Verified team context above. Even "
    "if you 'know' something from elsewhere — omit it. Player tenure and "
    "coach tenure are the only career-stage claims allowed.\n"
    "- PLAY-EVENT PRECISION: when describing how a player produced a result, "
    "keep separate events separate. Don't compress 'reached base via walk' + "
    "'later scored on a groundout' into a single phrase like 'reaching via "
    "walk and ultimately coming through' — that reads as if the walk drove "
    "the run in. Name each event distinctly. Same applies across sports: "
    "'stole the ball and ultimately knocked down the three' should make clear "
    "whether the steal led directly to the three-point shot or whether they "
    "were separate possessions.\n"
    "- ARITHMETIC CONSISTENCY: any 'N-game mark' / 'after N games' / 'through "
    "N games' framing MUST match wins + losses (+ ties / draws / OT losses "
    "where applicable) from the Verified team context. If the record is 25-27, "
    "the team has played 52 games, NOT 50, NOT 'around 50'. Same for win "
    "percentage / .500 framing: 25-27 is .481, NOT .500. Math is checkable; "
    "check it before writing the framing. Caught on 2026-05-22 when both Opus "
    "and Haiku wrote 'through 50 games' for a 25-27 record.\n"
    "- NO COMPARISON WITHOUT SOURCE: do not claim a stat is a 'season-high', "
    "'career-high', 'best of', 'lowest since', 'most in N games', 'first time "
    "since', or any other comparison-across-time UNLESS that comparison is "
    "explicitly present in the Verified team context or Story packet. A "
    "single per-game line in the boxscore is one data point — it tells you "
    "nothing about whether it's the season-high or career-high. Cite "
    "absolute numbers ('9 strikeouts in 7 innings') instead of unverifiable "
    "comparatives ('season-high in strikeouts').\n"
    "- HEDGE EARLY-SEASON CLAIMS: for plus-minus, win probability, lineup "
    "experiments, or any 'this team is X' framing in the first ~10 games of a "
    "season, hedge openly. Acknowledge sample-size limits."
)


# ── Claude API helper ──────────────────────────────────────────────────────────

# Cap web searches the writer can make per article. Story packets carry the
# per-game boxscore, so most stat claims should resolve from source without
# searching at all — this cap exists to bound cost AND reduce TPM consumption
# (each search call's results return into context, billing against the
# per-minute token cap). Lowered from 5 → 2 on 2026-05-22 to ease pressure
# on Anthropic's free-tier TPM ceiling. If the writer needs more context,
# the fix is enriching the KB / packet, not raising this cap.
WRITER_MAX_WEB_SEARCHES = 2

_SOURCE_HIERARCHY_RULE = (
    "- SOURCE HIERARCHY: when stating any factual claim, prefer in this order: "
    "(1) the Verified team context above, (2) the Story packet's boxscore / "
    "game_summary / standings_context, (3) web_search results from the "
    "authoritative-sources list below. NEVER state a stat or bio fact from "
    "memory without one of these three anchors.\n"
    "  Authoritative web sources (in priority order): ESPN.com, AP (apnews.com), "
    "the league's official site (MLB.com / NBA.com / NHL.com / NFL.com / WNBA.com "
    "/ MLS / NWSL / UFL), CBS Sports (cbssports.com), Yahoo Sports, the team's "
    "official site, The Athletic, NBC Sports, Sports Reference family "
    "(Baseball-Reference / Basketball-Reference / Pro-Football-Reference / "
    "Hockey-Reference), major regional newspaper coverage (Washington Post for "
    "DMV teams). Avoid social media, fan blogs, fan wikis as primary sources.\n"
    "- BOXSCORE DISCIPLINE: when the Story packet includes a per-player "
    "boxscore, EVERY per-player stat in the article MUST come verbatim from "
    "those rows — whatever stats the sport tracks (points/runs/goals, "
    "shooting/batting/pitching splits, rebounds, assists, +/-, time played). "
    "Do not round, paraphrase, or compute derived metrics like shooting "
    "percentages — cite the raw made/attempted (or other source-form) values "
    "and let readers do the math.\n"
    "- WEB SEARCH USE: you have web_search available. Use it ONLY to verify or "
    "fetch facts NOT in the Verified team context or Story packet — e.g. a "
    "player's college if you want to mention it. Always cite the URL inline. "
    "Do NOT search for stats that already appear in the boxscore."
)


def generate_article(game_summary, team, article_type="recap", target_date=None):
    """Call Claude to write a sports article based on game data.

    `target_date` is used to look up a same-date story packet at
    data/packets/{slug}_{YYYY-MM-DD}.json. If found, packet content (including
    full per-player boxscores when available) is injected into the prompt
    alongside the timeless KB block. The writer also has web_search enabled
    as a fallback for facts not in the source set.
    """
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set.")
        return None

    persona_name = team.get("persona") or "an NSMT writer"
    persona_voice = team.get("voice") or "professional and engaging"

    kb = load_team_kb(team)
    kb_block = kb_context_block(kb)

    packet = load_story_packet(team, target_date) if target_date else None
    packet_block = consume_story_packet(packet) if packet else ""

    if article_type == "recap":
        prompt = f"""You are {persona_name}, a sports writer covering DMV teams. Your voice: {persona_voice}.
{kb_block}{packet_block}
Write a professional, engaging game recap article (400-550 words) for the following game. Open with the moment that decided the game — the specific play, the missed shot, the called third strike — not with framing about coverage.

Team: {team['name']}
League: {team['league']}
Matchup: {game_summary['matchup']}
Final Score: {game_summary['score']}
Venue: {game_summary['venue']}
Top Performers: {', '.join(game_summary['leaders']) if game_summary['leaders'] else 'Not available'}

Coverage:
- Lead with the moment that decided it (specific play, turning point)
- Standout individual performances with one or two concrete numbers, not a stat dump
- Context about standings or season implications, briefly
- Close on a specific stat, quote, or one-line punch — NOT "looking ahead" or "only time will tell"

{NO_META_COMMENTARY}

{AI_TELLS_AVOIDANCE}

Voice + sourcing:
- Stay in your voice ({persona_voice}) — written for DC/MD/VA sports fans.
- Format: plain paragraphs only, no headers or bullet points.

Editorial guardrails (HARD requirements):
{GUARDRAILS}
{_SOURCE_HIERARCHY_RULE}

Also provide at the very end, on a new line starting with EXCERPT: a one-sentence teaser (max 160 characters) for the article preview."""

    elif article_type == "preview":
        prompt = f"""You are {persona_name}, a sports writer covering DMV teams. Your voice: {persona_voice}.
{kb_block}{packet_block}
Write a professional game preview article (350-450 words) for the upcoming game. Open with a specific storyline, matchup edge, or stake — not with framing about coverage.

Team: {team['name']}
League: {team['league']}
Matchup: {game_summary['matchup']}
Venue: {game_summary['venue']}

Coverage:
- Preview the matchup and what's at stake
- Key players to watch on both sides with one specific reason each
- Recent form or storylines where relevant

{NO_META_COMMENTARY}

{AI_TELLS_AVOIDANCE}

Voice + sourcing:
- Stay in your voice ({persona_voice}) — written for DC/MD/VA fans.
- Format: plain paragraphs only, no headers or bullet points.

Editorial guardrails (HARD requirements):
{GUARDRAILS}
{_SOURCE_HIERARCHY_RULE}

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
                "model": "claude-sonnet-4-6",
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": prompt}],
                "tools": [{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": WRITER_MAX_WEB_SEARCHES,
                }],
            },
            timeout=180,
        )
        resp.raise_for_status()
        # web_search responses interleave text + tool_use + tool_result blocks.
        # Concatenate all text blocks for the final article body.
        content_blocks = resp.json().get("content", [])
        text_chunks = [b["text"] for b in content_blocks if b.get("type") == "text"]
        return "\n\n".join(text_chunks) or None
    except Exception as e:
        print(f"  Claude API error: {e}")
        return None


# ── Adversarial fact-check pass ───────────────────────────────────────────────
#
# Added 2026-05-22 after the Mystics demo eval. Calls Sonnet 4.6 with
# Anthropic's web_search server tool enabled and a 5-tier claim grade:
#
#   ✅ SUPPORTED                   — true (verified via source OR web)
#   ⚠️  OUT_OF_SOURCE_BUT_VERIFIED — true, but writer pulled from outside
#                                    the source set we handed them (process
#                                    note, not a factual error)
#   💬 EDITORIAL                   — subjective judgment, not falsifiable
#                                    (e.g. "best game of his career") —
#                                    flagged for visibility but doesn't fail
#                                    the article. Added 2026-05-22 after a
#                                    Codex review FAIL'd an article for an
#                                    editorial claim that was reasonable
#                                    sports-writer language.
#   ❓ UNVERIFIED                  — couldn't be confirmed by web search
#   ❌ FALSE                       — contradicted by web or source
#
# Article-level verdict from claim mix:
#   PASS              — all ✅ + ⚠️ + 💬 (factually clean; opinions allowed)
#   NEEDS_REVISION    — any ❓
#   FAIL              — any ❌
#
# Never blocks admin save — verdict is informational, surfaced on the Discord
# embed for the human reviewer. The external codex_review.py launchd job is
# the more rigorous independent pass.

FACT_VERDICTS = {"PASS", "NEEDS_REVISION", "FAIL", "UNKNOWN"}

# Cap web searches per fact-check call. Each search result returns into the
# model's context, counting against TPM. Lowered from 10 → 2 on 2026-05-22
# to ease free-tier TPM pressure. Two searches are usually enough to verify
# a few key claims (a box score URL + a bio detail); the rest of the
# fact-check leans on the source data already in the prompt.
FACT_CHECK_MAX_WEB_SEARCHES = 2


def fact_check_article(article_text, kb, packet, team):
    """Returns (verdict, full_report) where verdict is one of FACT_VERDICTS.

    Calls Sonnet 4.6 with web_search enabled so the checker can actually
    verify claims against ESPN/WNBA.com/team-official sources, not just
    check whether claims appear in the in-prompt source data.

    Every call (success or failure) appends one line to
    data/fact_check_log.jsonl so we can answer effectiveness questions
    empirically over time (verdict distribution, agreement with Codex,
    cost trajectory).
    """
    fc_start = time.time()
    if not ANTHROPIC_API_KEY:
        _log_fact_check(team, "UNKNOWN", "(no API key)", 0.0)
        return ("UNKNOWN", "(skipped — ANTHROPIC_API_KEY not set)")
    if not article_text:
        _log_fact_check(team, "UNKNOWN", "(empty article)", 0.0)
        return ("UNKNOWN", "(skipped — empty article)")

    source_data = json.dumps(
        {"team": team.get("name"), "kb": kb or {}, "packet": packet or {}},
        indent=2,
        default=str,
    )

    prompt = f"""You are a meticulous sports fact-checker. You are paid to find errors, not approve articles. You have web search available — USE IT to verify factual claims against authoritative sources.

You have TWO sources of truth:
1. The structured source data block below (the team KB + any story packet the writer was given). This is the data the writer was supposed to draw from.
2. The open internet. Authoritative sources in priority order: ESPN.com, AP (apnews.com), the league's official site (MLB.com / NBA.com / NHL.com / NFL.com / WNBA.com / MLS / NWSL / UFL), CBS Sports, Yahoo Sports, the team's official site, The Athletic, NBC Sports, Sports Reference family (Baseball-Reference / Basketball-Reference / Pro-Football-Reference / Hockey-Reference), and major regional newspaper coverage (Washington Post for DMV teams). Avoid social media / fan blogs / unsourced wikis as primary sources.

Your job: extract every factual or judgment-style claim in the article (records, scores, stat lines, dates, opponents, venues, player names, scoring runs, win-probability claims, ranking claims, attendance, draft years, career stages, coaching staff, ownership, biographical details, AND editorial assertions like "best game of his career" / "the turning point was X"). For each claim, do this:

A. Check the structured source data block.
B. If it's not in the source block, search the web. Use the authoritative sources above. Cite the URL(s) you used.
C. Grade the claim with the 5-tier shape:
   ✅ SUPPORTED                   — verified true (in source data OR confirmed via web; cite source)
   ⚠️  OUT_OF_SOURCE_BUT_VERIFIED — true, but not in the structured source data we handed the writer (process note: writer pulled from outside source)
   💬 EDITORIAL                   — subjective/judgment claim that is not strictly falsifiable. Examples: "best game of his career," "showed grit," "the game turned on X," "looked tired in the late innings." Sports writers are allowed to make these, but flag them so the human reviewer sees what's being asserted as opinion vs. fact.
   ❓ UNVERIFIED                  — factual claim you couldn't confirm via web search (uncertain, needs human eye)
   ❌ FALSE                       — contradicted by web or source data; demonstrably wrong

Be precise about which web sources you used. A claim is ❌ FALSE only if you actively found contradicting authoritative evidence. If web search returns nothing definitive, the claim is ❓ UNVERIFIED — do NOT mark it ❌ just because it's missing from the structured source data. And if a claim is opinion/judgment rather than verifiable fact, mark it 💬 — do NOT mark it ❌ just because you can't verify a subjective judgment.

Structured source data (JSON):
```
{source_data}
```

Article:
```
{article_text}
```

Output format (strict — keep this format even after using web search):

VERDICT: PASS | NEEDS_REVISION | FAIL

(PASS = every claim is ✅ / ⚠️ / 💬. NEEDS_REVISION = at least one ❓ but no ❌. FAIL = at least one ❌.)

CLAIMS:
1. "[exact quote from article]" → ✅/⚠️/💬/❓/❌  [reason + citation, e.g. "ESPN box score confirms 9-of-15 FG (espn.com/...)" or "not found on ESPN, MLB.com, or AP" or "subjective judgment — not verifiable via source"]
2. ...

SUMMARY: [2-3 sentences naming the most serious factual issues, or "no factual issues found" — note 💬 editorial claims + ⚠️ process flags separately if relevant]

Do not invent issues. Do not be lenient on ❌. But ALSO do not mark a claim ❌ when web search confirms it (those go in ⚠️), and do not mark a subjective judgment ❌ just because you can't verify it (those go in 💬)."""

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
                "max_tokens": 4096,
                "temperature": 0.0,
                "messages": [{"role": "user", "content": prompt}],
                "tools": [{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": FACT_CHECK_MAX_WEB_SEARCHES,
                }],
            },
            timeout=180,
        )
        resp.raise_for_status()
        # Web-search-enabled responses contain interleaved text + tool_use
        # + tool_result blocks. Concatenate all text blocks for the report.
        content_blocks = resp.json().get("content", [])
        text_chunks = [b["text"] for b in content_blocks if b.get("type") == "text"]
        report = "\n\n".join(text_chunks).strip() or "(empty response)"
    except Exception as e:
        print(f"  Fact-check API error: {e}")
        _log_fact_check(team, "UNKNOWN", str(e), round(time.time() - fc_start, 1))
        return ("UNKNOWN", f"(fact-check call failed: {e})")

    verdict = _parse_verdict(report)
    _log_fact_check(team, verdict, report, round(time.time() - fc_start, 1))
    return (verdict, report)


def _log_fact_check(team, verdict, report, fc_seconds):
    """Append one line to data/fact_check_log.jsonl per fact-check call.

    Records timestamp, team, model used, verdict, tier counts, and elapsed
    seconds. We can read this back later to answer questions like:
    - What % of articles are passing vs failing?
    - Does the verdict distribution differ by team / sport?
    - When the in-line check + Codex disagree, what's the pattern?

    Never raises — logging failure must not break the fact-check pipeline.
    """
    try:
        import re as _re
        log_dir = Path(__file__).resolve().parent / "data"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "fact_check_log.jsonl"
        tier_counts = {
            "supported":  len(_re.findall(r"✅", report or "")),
            "verified":   len(_re.findall(r"⚠️", report or "")),
            "editorial":  len(_re.findall(r"💬", report or "")),
            "unverified": len(_re.findall(r"❓", report or "")),
            "false":      len(_re.findall(r"❌", report or "")),
        }
        entry = {
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "team_slug":   team_slug(team) if team else None,
            "team_name":   (team or {}).get("name"),
            "model":       "claude-sonnet-4-6",
            "verdict":     verdict,
            "fc_seconds":  fc_seconds,
            "tier_counts": tier_counts,
            "report_len":  len(report or ""),
        }
        with log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # never break the pipeline on a log write


def _parse_verdict(report):
    """Extract the article-level verdict from a fact-check report. Tolerant
    of leading markdown decoration (e.g. '**VERDICT: FAIL**') because the
    web_search-enabled responses often arrive with markdown formatting."""
    for line in report.splitlines():
        s = line.strip().strip("*").strip().upper()
        if not s.startswith("VERDICT:"):
            continue
        v = s.split(":", 1)[1].strip().strip("*").strip()
        if v.startswith("PASS"):
            return "PASS"
        if "FAIL" in v:
            return "FAIL"
        if "NEEDS_REVISION" in v or "NEEDS REVISION" in v:
            return "NEEDS_REVISION"
    return "UNKNOWN"


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


_VERDICT_COLORS = {
    "PASS":           0x2ECC71,
    "NEEDS_REVISION": 0xE67E22,
    "FAIL":           0xE74C3C,
    "UNKNOWN":        NSMT_BLUE,
}

_VERDICT_BADGES = {
    "PASS":           "✅ PASS",
    "NEEDS_REVISION": "⚠️ NEEDS_REVISION",
    "FAIL":           "❌ FAIL",
    "UNKNOWN":        "❓ UNKNOWN",
}


def build_fact_check_embed(team, verdict, report):
    """Build a fact-check embed dict (does not post). Returned dict slots
    into the same webhook payload as the article embed — forum-channel posts
    can carry up to 10 embeds in one message, and we send the article +
    fact-check report together so the reviewer sees both at once and we
    sidestep the "follow-up needs thread_id" problem."""
    MAX_DESC = 3800
    text = (report or "").strip() or "(no report)"
    if len(text) > MAX_DESC:
        text = text[:MAX_DESC].rstrip() + "…"
    return {
        "title":       f"🔍 Fact-check — {team['name']} — {_VERDICT_BADGES.get(verdict, verdict)}",
        "description": f"```\n{text}\n```"[:MAX_DESC],
        "color":       _VERDICT_COLORS.get(verdict, NSMT_BLUE),
        "footer":      {"text": "claude-sonnet-4-6 with web_search · independent of codex_review.py"},
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    }


def post_recap_to_discord(title, body, team, summary, game_date, fact_verdict="UNKNOWN", fact_report=None):
    """Best-effort notification to Discord via the Cloudflare Worker proxy.

    Routes to the team's own channel if `team["channel_target"]` matches a
    configured `DISCORD_WEBHOOK_URL_<X>` secret on the worker. Otherwise the
    worker falls back to the default webhook (currently #recap-pipeline via
    the RECAPS target).

    Posts the article body + (when verdict != PASS) the fact-check report
    as two embeds in a single webhook call. Forum channels reject follow-up
    posts that don't reference an existing thread, so we batch instead of
    chasing the thread_id roundtrip — Discord supports up to 10 embeds per
    message and the article + fact-check fits comfortably in two.

    Never raises — Discord failure must not block admin saves.
    """
    if not DISCORD_PROXY_URL or not DISCORD_PROXY_SECRET:
        print("  Discord notification skipped — DISCORD_PROXY_URL / DISCORD_PROXY_SECRET not set.")
        return False

    MAX_DESC = 3900
    body_text = (body or "").strip() or "(no body provided)"
    if len(body_text) > MAX_DESC:
        body_text = body_text[:MAX_DESC].rstrip() + "…\n\n[Continue reading in admin →](" + ADMIN_REVIEW_URL + ")"

    channel_target = team.get("channel_target") or DISCORD_TARGET
    byline = build_byline(team)
    verdict_badge = _VERDICT_BADGES.get(fact_verdict, _VERDICT_BADGES["UNKNOWN"])
    embed_color = _VERDICT_COLORS.get(fact_verdict, _VERDICT_COLORS["UNKNOWN"])

    article_embed = {
        "title":       f"📝 New Recap Draft — {team['name']}",
        "description": body_text,
        "color":       embed_color,
        "fields": [
            {"name": "✍️ Byline",      "value": byline,                                    "inline": False},
            {"name": "🏆 Game",        "value": summary.get("score", "Score unavailable"), "inline": False},
            {"name": "🔍 Fact-check",  "value": verdict_badge,                             "inline": True},
            {"name": "🤖 Model",       "value": "claude-sonnet-4-6",                       "inline": True},
            {"name": "✏️ Review",      "value": f"[Open in admin]({ADMIN_REVIEW_URL})",    "inline": False},
        ],
        "footer":    {"text": f"{team['league']} · status: draft (is_active=0) in admin"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    embeds = [article_embed]
    if fact_report and fact_verdict in {"NEEDS_REVISION", "FAIL"}:
        embeds.append(build_fact_check_embed(team, fact_verdict, fact_report))

    thread_name = f"{team['name']} — {game_date.isoformat()}"
    if len(thread_name) > 100:
        thread_name = thread_name[:99] + "…"

    payload = {"thread_name": thread_name, "embeds": embeds}

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
            print(f"  ✓ Discord notification posted to target='{channel_target}' (status {resp.status_code}, {len(embeds)} embed(s))")
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

def run(target_date=None, team_slug_filter=None):
    """Generate recaps for all in-season DMV teams that played on `target_date`.

    `team_slug_filter` scopes the run to a single team (matches the slug from
    `_TEAM_SLUG_MAP`). Useful for cost-controlled testing via workflow_dispatch
    without iterating the full TEAMS list.
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)  # yesterday by default

    print(f"\nNSMT Content Pipeline — {target_date.isoformat()}")
    if team_slug_filter:
        print(f"  scoped to team_slug={team_slug_filter!r}")
    print("=" * 50)

    # Get a single fresh token for this run
    token = get_nsmt_token()
    if token:
        print("✓ Authenticated with thensmt.com")

    articles_generated = 0
    fetched = {}

    skipped_offseason = []
    skipped_filter = []
    for team in ALL_TEAMS:
        if team_slug_filter and team_slug(team) != team_slug_filter:
            skipped_filter.append(team["name"])
            continue
        if not in_season(team, target_date):
            skipped_offseason.append(team["name"])
            continue

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
        article_text = generate_article(summary, team, article_type="recap", target_date=target_date)

        if not article_text:
            print(f"  {team['name']}: article generation failed, skipping.")
            continue

        # Split body and excerpt
        body_raw = article_text
        excerpt = ""
        if "EXCERPT:" in article_text:
            parts = article_text.rsplit("EXCERPT:", 1)
            body_raw = parts[0].strip()
            excerpt  = parts[1].strip()

        # In-line fact-check (Sonnet 4.6 + web_search). Default OFF — set
        # NSMT_FACT_CHECK=true to enable. Tonight's 3-model comparison showed
        # Codex (free via ChatGPT sub) reaches the SAME verdict as the in-line
        # Sonnet check for every article we compared. The in-line check costs
        # ~$0.10-0.25/article × 14 teams/day = $42-105/month with no verdict-
        # level signal beyond what the codex_review.py launchd job produces
        # at 8:05am next day. Flip NSMT_FACT_CHECK=true for the rare high-
        # stakes article that needs same-second verdict on the Discord embed.
        if os.environ.get("NSMT_FACT_CHECK", "").lower() in ("1", "true", "yes"):
            kb_for_check = load_team_kb(team)
            packet_for_check = load_story_packet(team, target_date)
            fact_verdict, fact_report = fact_check_article(body_raw, kb_for_check, packet_for_check, team)
            print(f"  Fact-check: {fact_verdict}")
        else:
            fact_verdict, fact_report = "UNKNOWN", None
            print("  Fact-check skipped (NSMT_FACT_CHECK not set). Codex review will provide verdict.")

        # body_raw goes to Discord (markdown-friendly). body_html goes to admin
        # (wrapped in <p> tags for the rich text editor).
        body_html = "".join(f"<p>{p.strip()}</p>" for p in body_raw.split("\n\n") if p.strip())

        title = f"{summary['score']} | {team['name']} Recap"
        slug  = slugify(f"{team['name']}-recap-{target_date.isoformat()}")

        saved = save_to_nsmt(title, slug, body_html, excerpt, team, target_date, token)
        if saved:
            post_recap_to_discord(
                title, body_raw, team, summary, target_date,
                fact_verdict=fact_verdict, fact_report=fact_report,
            )
        else:
            save_local_draft(title, body_raw, team, target_date)

        articles_generated += 1

    if skipped_offseason:
        print(f"\nSkipped (out of season): {', '.join(skipped_offseason)}")
    if skipped_filter:
        print(f"Skipped ({len(skipped_filter)} teams — outside team_slug filter)")

    print(f"\nDone. {articles_generated} article(s) generated for {target_date.isoformat()}.")
    print("Review drafts at: https://admin.thensmt.com/#/blogs")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Daily content pipeline.")
    parser.add_argument("date", nargs="?", default=None,
                        help="Target date YYYY-MM-DD (default: yesterday).")
    parser.add_argument("--team", default=None,
                        help="Single team slug to process (e.g. 'nationals'). "
                             "When provided, all other teams are skipped. "
                             "Use for cost-controlled testing.")
    args = parser.parse_args()
    target = None
    if args.date:
        from datetime import datetime
        target = datetime.strptime(args.date, "%Y-%m-%d").date()
    run(target, team_slug_filter=args.team)
