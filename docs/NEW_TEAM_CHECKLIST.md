# Adding a New Team or Sport — Checklist

Use this when extending the pipeline to a new team (e.g., DC Defenders) or a
new sport (e.g., MLB, NHL, NFL). Each section references the canonical
pattern in `docs/LESSONS_LEARNED.md`.

This is a literal checklist — don't trust your memory of "what to do," check
each item against the code.

---

## Phase 1 — KB file (`data/teams/{slug}.json`)

Required for the existing prompt pipeline to render the team's KB block
cleanly. Use `data/teams/mystics.json` as the reference shape.

- [ ] `team_name` — string, full official name (e.g. "Washington Mystics").
- [ ] `slug` — string, kebab-case (e.g. "mystics"). Must match the filename
      and the entry in `_TEAM_SLUG_MAP` (see Phase 3).
- [ ] `league` — string. Must be a key in `LEAGUE_SEASONS`
      (`generate_content.py:55`) or in-season gating fails and the team is
      always skipped.
- [ ] `conference`, `division` — optional, render in KB block if present.
- [ ] `current_season` — string. First 4 chars are used as the year by
      `_derive_player_tenure` and `_derive_coach_tenure`. For pro leagues
      that span a calendar year (NBA, NHL) decide whether to use the start
      year or end year and be consistent.
- [ ] `current_record` — string, e.g. "2-2 (as of YYYY-MM-DD)".
- [ ] `head_coach` — object with at minimum `name` and `tenure_start`.
      Optional `background` shows up in the KB but is currently not used
      by tenure derivation. `tenure_start` is the year the coach took the
      job; coach tenure derivation reads its first 4 chars.
- [ ] `roster` — list of objects with `name`, `position`, `number`, `notes`.
      For tenure-eligible players, `notes` should contain a draft-year
      string the parser recognizes (`_derive_player_tenure` matches one of:
      `"{YYYY} No. {N} overall draft pick"`, `"drafted {YYYY}"`,
      `"{YYYY} draft"`). Players without a draft note get rendered in the
      roster block but get no tenure line.
- [ ] `recent_games` — list of game dicts: `date` (ISO date),
      `opponent` (string), `result` (string like "W 68-65" or
      "L 98-93 OT"), `venue` ("home" or "away"). The KB block renders the
      last 3 by default.
- [ ] `upcoming_games`, `rivalries`, `venue`, `ownership`, `front_office`,
      `coaching_staff` — optional but nice to have.
- [ ] `sources`, `verification_notes`, `last_updated` — provenance fields.
      Not used by the prompt but valuable when auditing the KB.

---

## Phase 2 — packet ingestion (per game)

Packet ingestion is currently Mystics-only. See `ingestion/` for the shape.

### If the new team is in the SAME sport as an existing one (e.g., another WNBA team)

1. The fetcher in `ingestion/fetchers/espn.py` is hardcoded for Mystics
   (`TEAM_NAME`, `ESPN_TEAM_ID`). Generalize to take team identity as a
   parameter, or copy and rename.
2. `ingestion/generate_story_packet.py` checks
   `if team != TEAM_SLUG: raise ValueError(...)`. Loosen this once another
   team is supported.
3. The `BoxscoreRow` shape in `ingestion/schema.py:70` carries
   basketball labels (PTS / REB / AST / FG / 3P / FT / +/-). For another
   basketball team this just works. For another sport, see the next section.

### If the new team is in a DIFFERENT sport (MLB, NHL, NFL, MLS, NWSL, UFL)

The current `BoxscoreRow` (line 70 in `ingestion/schema.py`) is shaped for
basketball. Other sports have fundamentally different stat categories.
Pick an approach before writing code:

- **Option A — extend BoxscoreRow** with sport-specific optional fields
  (`hits`, `runs`, `era`, `passing_yards`, `goals`, etc.). Cheap, but the
  TypedDict gets messy as more sports land.
- **Option B — introduce sport-specific TypedDicts** (`MlbBattingRow`,
  `MlbPitchingRow`, `NhlSkaterRow`, `NflStatRow`, etc.). Cleaner
  long-term. The packet schema would need a sport tag or sport-specific
  boxscore fields.
- **Option C — embrace the writer's `web_search`** and skip building
  packet ingestion for the new sport entirely. The writer's `web_search`
  fallback (capped at 5 uses) can pull boxscores live from ESPN. Risk:
  more invented stats when search returns nothing clean. Trade-off:
  zero ingestion code per new sport.

`_format_boxscore_rows` in `generate_content.py:476` is also basketball-
shaped. Either parameterize by sport or add a sport-specific renderer.

ESPN's JSON shape differs by sport — the stat labels and the
`boxscore.players[*].statistics` structure are not stable across leagues.
Verify with a real ESPN summary endpoint for the new sport before writing
the fetcher.

---

## Phase 3 — wire the team into the existing pipeline

1. Add the team to `TEAMS` or `COLLEGE_TEAMS` in `generate_content.py`
   (around line 96 / 135). Required fields per the existing dicts:
   `name`, `league`, `espn_id`, `sport`, `league_slug`, `category`,
   `persona`, `voice`, `channel_target`.
2. Add the (name, league) → slug mapping to `_TEAM_SLUG_MAP`
   (`generate_content.py:246`). `team_slug()` won't resolve without this.
3. No action needed for codex review — `scripts/codex_review.py:203`
   (`find_team_for_thread`) matches threads against `ALL_TEAMS` by team
   name / byline persona, so any team added via step 1 above is
   automatically eligible. Note: codex review currently relies on `KB +
   per-day packet` as the source set. If the new team has no packet
   ingestion built (Phase 2 skipped), expect more ❓ UNVERIFIED claims
   in the second-opinion report.
4. If the team has its own Discord channel, set `channel_target` to the
   matching Cloudflare Worker target name and add the
   `DISCORD_WEBHOOK_URL_<TARGET>` secret on the worker.

---

## Phase 4 — validate before merging into the daily cron

Run through this before adding the team to the production cron's run.

- [ ] **KB renders cleanly**: in a Python REPL,
      `from generate_content import load_team_kb, kb_context_block` →
      print `kb_context_block(load_team_kb({"name": ..., "league": ...}))`.
      Verify the KB block shows roster, recent_games, head_coach with
      derived tenure, and the BIOGRAPHICAL LOCKDOWN guardrails will catch
      any gaps the model might try to fill.
- [ ] **Tenure derivation fires correctly**: confirm no false positives
      (a coach incorrectly getting "in 2nd year" framing because
      `tenure_start` was misread) and no false negatives (a drafted player
      whose note format the parser didn't recognize).
- [ ] **Packet generates** (if Phase 2 work was done):
      `python -m ingestion.generate_story_packet --team {slug} --date YYYY-MM-DD --dry-run`
      should validate cleanly. Verify `boxscore` and `opponent_boxscore`
      are populated for game-day packets.
- [ ] **Recap prompt renders**: simulate a recap call without invoking
      the API. The prompt should include the KB block, the packet block
      (when present), the GUARDRAILS, and the `_SOURCE_HIERARCHY_RULE`.
- [ ] **Trigger an end-to-end test via GH Actions** with a known recent
      game. Check that the Discord post is one message with both the
      article embed and (when verdict ≠ PASS) the fact-check embed.
- [ ] **Run `scripts/codex_review.py --since-hours 1 --wait-minutes 0`**
      after the post lands to get the second-opinion verdict.
- [ ] **Manually cross-check 3-5 claims** in the article against ESPN
      (or whichever league source) to verify accuracy. Any ❌ flagged by
      either fact-checker that the writer disagrees with is signal worth
      digging into.

---

## Don'ts

- Don't duplicate `GUARDRAILS` in a new demo or one-off script. Import it
  from `generate_content` (see `LESSONS_LEARNED.md` §7).
- Don't write a new Discord poster that uses separate webhook calls for
  the article and the fact-check report. Bundle embeds (see §5).
- Don't add a new fact-checker without `web_search` and the 4-tier
  verdict shape (see §2).
- Don't pass raw KB notes to the writer and hope it infers correctly.
  Pre-compute the canonical statement in the KB block (see §1).
- Don't trust stat lines from the writer when no packet boxscore is in
  the source set. If the new team doesn't have packet ingestion built
  yet, expect the writer's `web_search` to be the only safety net — and
  expect it to occasionally miss (see §3).
- Don't add a new team to `ALL_TEAMS` before doing Phase 4. A broken team
  on the daily cron burns API credits on every run.
