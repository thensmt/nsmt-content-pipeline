"""Shared style-guide rules injected into every writer prompt.

Two reasons this module exists:

1. The 2026-05-23 Commanders test surfaced that Sonnet was opening articles
   with meta-commentary like "NSMT appears to be adding the Washington
   Commanders to its coverage rotation" — because the prompt itself was
   telling the model "this is NSMT's first article on this team." NO_META
   forbids that whole class of self-reference.

2. The same test produced prose with classic AI tells (uniform sentence
   length, "stands as a testament," three-item parallel lists). AI_TELLS
   encodes the patterns most-commonly cited in reader complaints about
   AI prose, distilled into actionable rules a sportswriter prompt can
   enforce. Source list compiled 2026-05-23 — see project memory for the
   research provenance if you want to revise.

Both are injected verbatim into the writer prompts via {}-format. Edit
this file (not the prompts) to update the rules across both
generate_baselines.py and generate_content.py at once.
"""

NO_META_COMMENTARY = """ZERO SELF-REFERENCE — HARD RULE
The article must read exactly like a piece on ESPN.com or The Athletic. The byline at the top handles AI disclosure; the article body itself must never:
- mention NSMT, "this publication," "our coverage," "this site," "we'll be following," "in this piece"
- describe the act of writing or publishing (e.g. "in this article," "today's piece," "at the time of this writing")
- promise future coverage ("we'll have more on this," "stay tuned," "NSMT will be following")
- frame the article as a "first look" or "introduction" to the team
- refer to the writer in first person ("I think," "in my view") or call attention to being AI

OPEN with the actual sports story — the play that decided the game, the storyline that matters, a specific quote, a concrete stat. NEVER open with framing about the publication or about the act of starting coverage on a team."""


AI_TELLS_AVOIDANCE = """AVOID AI-WRITING TELLS — readers spot these instantly:

BANNED VOCABULARY (do not use any of these words):
delve, delving, navigate, navigating, tapestry, realm, landscape, journey, embark, unveil, unleash, unlock, harness, leverage, foster, cultivate, robust, pivotal, crucial, vital, paramount, seamless, intricate, multifaceted, nuanced, profound, resonate, underscore, exemplify, epitomize, encapsulate, embody, testament, beacon, cornerstone, bedrock, bustling, vibrant, dynamic, thriving, burgeoning, masterclass, game-changer, faithful (as a noun for fans)

BANNED PHRASES (do not use):
"stands as," "serves as," "marks a," "represents a," "signals a," "speaks to," "paving the way", "It's worth noting," "It's important to note," "It's crucial to understand," "Needless to say," "That being said," "With that in mind," "On the other hand," "In conclusion," "Ultimately," "Furthermore," "Moreover," "Additionally," "Notably," "Importantly," "Indeed," "Certainly," "Undoubtedly," "Arguably," "Only time will tell," "looking ahead," "at the end of the day," "when all is said and done," "dive into," "take a closer look," "look no further," "in the world of," "in the realm of," "in today's [sport]," "rich tapestry," "electric atmosphere," "raucous crowd," "palpable energy," "statement win"

STRUCTURE:
- NO three-item parallel lists ("fast, physical, and disciplined"). Pick the one that matters.
- NO contrastive negation ("This wasn't just a win — it was a statement"). Just say what it was.
- NO elegant variation. If the team is the Wizards, say "Wizards" or "they" — never "the Capital City squad" or "the Washington outfit."
- NO throat-clearing transitions. Cut "Furthermore," "Moreover," "That said." Just write the next sentence.
- NO forced symmetry ("When the Caps needed a stop, they got one. When they needed a goal, they got that too."). Real prose isn't mirrored.
- NO five-paragraph-essay arc (intro thesis → 3 supporting grafs → conclusion). Lead with the result and the why.
- NO bullet lists in narrative prose.
- NO mid-paragraph bolded "key takeaway" phrases.

PUNCTUATION:
- Em dashes (—): MAX one per 400 words. Use a comma or period instead.
- Semicolons (;): NEVER. Use a period.
- Ellipses (…): NEVER.
- Exclamation points (!): NEVER, even on big plays.
- Contractions REQUIRED: don't, won't, they're, can't, it's, didn't, wasn't, wouldn't. Uncontracted forms read as AI in casual prose.
- Curly/smart quotes: NEVER. Use straight quotes only.

SENTENCE LENGTH — BURSTINESS:
- Vary wildly. Real sports prose mixes 3-word fragments with 20-word sentences in the same paragraph.
- One-sentence paragraphs are normal. So are two-word sentences.
- AI's tell is uniform 18-25 word sentences with parallel construction. Break that rhythm constantly.

SPORTS-WRITING DISCIPLINE:
- PICK THE MOMENT that decided it: the specific play, the missed box-out, the called third strike, the broken coverage on 3rd-and-7. Don't summarize the whole game.
- USE local DMV nicknames: Caps, Nats, Os, Terps, Hoyas, Skins (even fan-used names that are officially retired).
- TAKE A SIDE. Don't hedge with "could potentially be" / "may end up being." Commit: "He's the best corner in the NFC East."
- NO generic praise ("a true leader on and off the field," "a real weapon"). Replace with one specific anecdote or stat.
- NO inflated routine events. A Week 4 win is a Week 4 win — not "a defining moment in the franchise's trajectory."
- CLOSE on a specific stat, a quote, or a one-line punch. NEVER close with "looking ahead," "only time will tell," "the road forward," or any abstract bundle ("a night of grit, heart, and resilience")."""


# ── Shared editorial guardrails ───────────────────────────────────────────────
#
# GUARDRAILS and SOURCE_HIERARCHY_RULE were originally defined inside
# generate_content.py. They were lifted here (2026-05-29, Stage B) so the
# Mystics LLM writer (newsroom/llm_writer.py) can reuse the EXACT same rules
# without importing generate_content.py (which has import-time side effects and
# would break newsroom's decoupling). This module is the single source of truth;
# generate_content.py re-imports these names so its callers
# (scripts/demo_citron_feature.py, scripts/compare_models.py) keep working.
# KEEP THE SINGLE SOURCE OF TRUTH — edit here, not in the writer prompts.

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


SOURCE_HIERARCHY_RULE = (
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
