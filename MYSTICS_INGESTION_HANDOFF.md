# Claude Code Handoff — Mystics Story Packet Ingestion Build

Repo root: `/Users/david/Downloads/Claude/NSMT/content-pipeline`
Stage: DEVELOP
Timestamp: 2026-05-22

---

## What you (next-session Claude) need to do

Launch the **`codex:codex-rescue`** subagent (via the Agent tool, `subagent_type: codex:codex-rescue`) and hand it the **Task spec** below. Codex will do the implementation. You orchestrate, review, and report back.

**Hard constraint: Codex MUST land its work on a feature branch named `feat/mystics-story-packet`, NOT on `main`.** Pass this explicitly in the prompt. Do not let it push to main.

When Codex finishes, review:
- Files changed (should be additive — new `ingestion/` module + a new `consume_story_packet()` stub already exists at `generate_content.py:342` and should be referenced, not duplicated)
- Sample `story_packet_mystics_<date>.json` output
- That `generate_content.py` was NOT modified beyond importable hooks
- Branch pushed cleanly with PR-ready commits

Surface a one-screen summary to David.

---

## Runtime context

- Python repo, deps currently only `requests` (see `.github/workflows/daily-content.yml`)
- Daily cron orchestrator is `generate_content.py`
- Existing KB files at `data/teams/{slug}.json` (timeless team context — DO NOT MODIFY)
- Story packets will live at `data/packets/{slug}_{YYYY-MM-DD}.json` (timely game enrichment)
- The integration contract is already defined: `consume_story_packet(packet)` at `generate_content.py:342`. Codex must read that function and design its packet JSON to fit.

---

## Task spec to give Codex

Paste the block below verbatim into the Codex subagent prompt:

````
TASK: Build a Mystics-only public-source ingestion MVP for the NSMT
content pipeline. This is an ADDITIVE layer — do not modify existing
pipeline behavior beyond exposing hooks.

BRANCH REQUIREMENT (hard):
- Create a new branch: feat/mystics-story-packet
- All commits land on that branch
- Push the branch to origin
- DO NOT push to main under any circumstance
- DO NOT open the PR — leave that for human review

REPO: https://github.com/thensmt/nsmt-content-pipeline
LOCAL: /Users/david/Downloads/Claude/NSMT/content-pipeline

READ THESE FIRST (mandatory):
1. generate_content.py — entire file. Note especially:
   - kb_context_block() at line ~290 (style guide for prompt blocks)
   - consume_story_packet() at line ~342 — THIS IS YOUR INTEGRATION
     CONTRACT. The JSON shape you produce MUST be consumable by this
     function. Do not modify this function; design TO it.
   - team_slug(), load_team_kb(), in_season(), LEAGUE_SEASONS
   - TEAMS list — Mystics entry has espn_id=14, league=WNBA
2. data/teams/mystics.json — the existing KB. Story packet COMPLEMENTS
   this; does not duplicate it.
3. .github/workflows/daily-content.yml — current CI shape.

GOAL: Produce a structured JSON story packet for the Mystics on
demand. No publishing changes. No Claude calls. No Contentful writes.

DELIVERABLES:

1. New module: ingestion/
   - ingestion/__init__.py
   - ingestion/generate_story_packet.py — the CLI entry point
   - ingestion/fetchers/  — one file per source (espn.py, wnba_com.py,
     mystics_official.py, reddit_stub.py)
   - ingestion/cache.py — local JSON caching
   - ingestion/validators.py — schema validation
   - ingestion/schema.py — Python dataclasses or TypedDicts that match
     the consume_story_packet() expected shape

2. CLI:
   python -m ingestion.generate_story_packet --team mystics
   python -m ingestion.generate_story_packet --team mystics --dry-run
   python -m ingestion.generate_story_packet --team mystics --date 2026-05-21

   Default behavior: write to data/packets/mystics_<YYYY-MM-DD>.json
   --dry-run: print packet JSON, validate, do not write

3. data/packets/.gitkeep (commit empty directory so structure is clear)

4. tests/test_story_packet.py — at minimum:
   - schema round-trip (build a packet, validate, consume via
     consume_story_packet, assert non-empty string)
   - off-day fallback (no game → event_type=off_day, news+standings only)

5. README.md update: new section "Story Packet Ingestion (MVP)" with
   - what it is
   - how to run
   - how to extend to other teams
   - status (Mystics only; consumer hookup deferred)

REQUIRED PACKET FIELDS (per consume_story_packet contract):
- team:                      str
- league:                    str
- event_type:                "game" | "news" | "injury" | "transaction" |
                             "standings_update" | "off_day"
- retrieved_at:              ISO 8601 UTC ("2026-05-22T14:30:00Z")
- kb_slug:                   pointer to data/teams/{slug}.json (e.g. "mystics")
- game_summary:              dict (score, venue, opponent, date) or null
- top_performers:            list of {player, stat_line, note}
- recent_team_context:       str (1-3 sentences)
- key_players:               list of {name, role}
- injuries_or_availability:  list of {player, status, note, source_url}
- standings_context:         str
- recent_news_items:         list of {title, url, published_at, source_name, confidence}
- editorial_angle_candidates: list[str] — 2-4 suggested angles, NOT mandates
- confidence_notes:          list[str] — gaps the writer must NOT fabricate around
- source_links:              list of {source_name, source_url, published_at,
                                       retrieved_at, confidence}

CONTROLLED VOCABULARIES (fixed — do not invent):
- event_type: the 6 values above only
- confidence: float 0.0–1.0 (per-source AND aggregate)
- All timestamps: ISO 8601 UTC

SOURCES TO IMPLEMENT (Mystics-first, team-extensible):
- ESPN WNBA scoreboard + team data (reuse generate_content.py patterns)
- WNBA.com Mystics schedule/box score/standings (HTTP, parse JSON or HTML)
- Washington Mystics official site/news
- Reddit/r/washingtonmystics: STUB ONLY — interface returns [], with
  TODO comment + NotImplementedError path documented

OFF-DAY BEHAVIOR:
- If no Mystics game on target date, still produce a valid packet
- event_type = "off_day"
- game_summary = null
- Populate from news/standings/injuries
- confidence_notes must list "no game played on {date}"

CACHING:
- Path: cache/{source_name}/{cache_key}.json
- Per-source TTL constants at top of cache.py:
  ESPN_TTL_MIN = 15
  WNBA_NEWS_TTL_MIN = 120
  OFFICIAL_SITE_TTL_MIN = 60
- Cache hit within TTL → read disk; miss/expired → fetch + write
- Add cache/ to .gitignore

SCRAPING RULES:
- User-Agent: "NSMT-StoryPacket/0.1 (+https://thensmt.com)"
- Respect robots.txt (use urllib.robotparser)
- 1s minimum sleep between requests to the same domain
- If a source returns 4xx/5xx/timeout: log, skip that source, add to
  confidence_notes — never crash the packet build

DEPENDENCIES:
- Pipeline currently uses only `requests`
- If you add beautifulsoup4 or lxml, update .github/workflows/daily-content.yml
- Avoid trafilatura/playwright/selenium — too heavy for this MVP

DO NOT:
- Modify generate_content.py (the consume hook is already there)
- Modify any data/teams/*.json file
- Call run() or any publishing function
- Push to main
- Open the PR
- Wire the consume hook into run() — that is a future PR

WHEN DONE, REPORT:
- Branch name + commit SHAs (in chronological order)
- Files created (full list)
- Sample packet output (the actual generated JSON for one --dry-run)
- How to run (3-5 lines)
- What needs to happen next to wire the packet into generate_content.py
- Any sources that returned no data + why
- Any gotchas the reviewer should know
````

---

## Definition of done for the orchestrator (you, next-session Claude)

After Codex returns:

1. Verify branch `feat/mystics-story-packet` exists on origin and is NOT merged
2. Verify `main` was not touched (git log on main should still end at the commit before Codex ran)
3. Verify `data/teams/mystics.json` was NOT modified
4. Verify `generate_content.py` was NOT modified (the consume hook stays as-is)
5. Run `python -m ingestion.generate_story_packet --team mystics --dry-run` to confirm it executes
6. Read Codex's sample output for sanity (real ESPN data? real news titles? confidence_notes populated when gaps exist?)
7. Report to David in <200 words: branch, what to review, any concerns

If Codex pushed to main: STOP. Tell David. Do not try to clean up without him.
