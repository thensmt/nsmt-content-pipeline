# Lessons Learned — NSMT Content Pipeline

This document captures architectural decisions made during the 2026-05-22
Mystics demo eval and the remediation work that followed. Read this before
extending the pipeline to a new team, sport, or article type — the patterns
below address failure modes that took a full evening of iteration to find.

Every claim cites a specific commit and the file/line where the pattern
lives. Verify against the code before trusting this document — code is the
source of truth, this is just the narrative.

---

## Context: the 2026-05-22 Mystics demo eval

A multi-session run produced four Mystics demo articles (two Opus 4.6, two
Sonnet 4.6) and ran an external fact-check via `scripts/demo_mystics_season.py`.
Three of four came back NEEDS_REVISION. The user's review identified the
real bottleneck wasn't writer-model quality — it was data grounding upstream
and editorial validation downstream.

Six commits to `main` (in order) addressed the issues:

1. `1a60cdc` — Tighten daily-recap pipeline after 2026-05-22 Mystics demo eval
2. `654e429` — Fix bio-claim handling + land Codex review pipeline on main
3. `cb656fd` — Add Citron player-feature demo + lift GUARDRAILS to module scope
4. `550de22` — Make fact-checkers actually verify — web search + 4-tier verdicts
5. `2f03530` — Fix verdict parser: tolerate markdown-bolded VERDICT lines
6. `af4e7f5` — Wire ESPN boxscore into packets + give writer web_search

---

## The lessons

### 1. Raw KB notes are not enough — pre-compute facts that require inference

**Failure mode.** The Mystics KB at `data/teams/mystics.json` lists Kiki
Iriafen with `notes: "2025 No. 4 overall draft pick"`. The KB block passed
this verbatim to the writer. Both Opus 4.6 and Sonnet 4.6 still described
her as "four games into her WNBA career" / treated her as a rookie in
multiple of the demo articles — the user's review called this "the biggest
repeated factual issue." The 2026 season is her second; the draft-year
inference was not made.

**Fix.** Pre-compute the canonical career-stage statement and render it
explicitly as a "Verified player tenure" section in the KB block. The model
is given an unambiguous fact rather than asked to compute one.

**Where in code:**
- `generate_content.py:311` — `_derive_player_tenure(notes, current_season, league)`
- `generate_content.py:345` — `_derive_coach_tenure(coach, current_season)`
- `generate_content.py:368` — `kb_context_block(kb)` (renders both tenures)
- `generate_content.py:307` — `_TENURE_ORDINALS` (shared lookup)

**Commits:** `1a60cdc` introduced player tenure derivation; `654e429` added
the coach equivalent.

**Reusable pattern:** any inference the model could plausibly get wrong
(career stage, tenure, role, status) should be pre-computed in the KB block
and labeled "Verified" so the model treats it as fact, not inference.

---

### 2. Source-consistency is not the same as truth-checking

**Failure mode.** The first-generation fact-checker passed only the source
data we handed the writer (KB + packet) and graded claims as ❌ when they
weren't in source — even when the claim was true. The 2026-05-22 Citron run
produced exactly this failure: the article said "Kiki Iriafen — now in her
second WNBA season"; the source packet didn't include her draft history;
the fact-checker marked it ❌ UNSUPPORTED even though Basketball-Reference
confirms she was drafted in the 2025 WNBA Draft (1st round, 4th pick).

**Fix.** Both fact-checkers now have web access:
- The in-line Sonnet pass uses Anthropic's `web_search_20250305` server tool.
- The Codex CLI pass is instructed in its prompt to web-search via ESPN /
  league-official / team-official sites and cite the URL it used.

A 4-tier claim taxonomy captures the new distinction between "wrong" and
"out of source":

- ✅ SUPPORTED — verified true (source OR web)
- ⚠️ OUT_OF_SOURCE_BUT_VERIFIED — true, but writer pulled from outside source
- ❓ UNVERIFIED — couldn't be confirmed via web search
- ❌ FALSE — contradicted by web or source data

Article-level verdict mapping: all ✅ + ⚠️ → PASS; any ❓ → NEEDS_REVISION;
any ❌ → FAIL.

**Where in code:**
- `generate_content.py:825` — `FACT_CHECK_MAX_WEB_SEARCHES = 10`
- `generate_content.py:828` — `fact_check_article(article_text, kb, packet, team)`
- `scripts/codex_review.py:235` — `review_with_codex(article, team, kb, packet)`

**Commit:** `550de22`.

---

### 3. Writers invent stats when the source has none — provide the boxscore

**Failure mode.** The first Citron demo run was given only final scores in
the KB's `recent_games` field — no per-player stats. For the May 15 Indiana
game Sonnet wrote that Citron "finished with 26 points on 9-of-15 shooting
from the field, connecting on 4-of-8 from three-point range and going
4-of-4 from the free-throw line." The web-enabled fact-checker later
verified the real line via Fox Sports / CBS Sports as 30 points on
10-of-14 FG, 1-of-4 from three, 9-of-10 from the free-throw line. Every
number in the article's Citron stat line was wrong.

**Fix.** The ESPN summary endpoint already returns full per-player
boxscores; the existing fetcher pulled them for top-5 selection and then
discarded the rest. The fetcher now extracts the full boxscore for BOTH
teams and the packet includes them under optional `boxscore` /
`opponent_boxscore` fields. The writer prompt's BOXSCORE DISCIPLINE rule
demands verbatim citation — no rounding, no paraphrasing, no computed
shooting percentages.

**Where in code:**
- `ingestion/schema.py:70` — `BoxscoreRow` TypedDict
- `ingestion/schema.py:87` — `TeamBoxscore` TypedDict
- `ingestion/schema.py:94` — `StoryPacket` (now `total=False` with optional fields)
- `ingestion/schema.py:119` — `REQUIRED_PACKET_FIELDS` (kept explicit so adding optional fields doesn't break older callers)
- `ingestion/fetchers/espn.py` — `_extract_team_boxscore(event, summary, mystics)`
- `generate_content.py:476` — `_format_boxscore_rows(boxscore)`
- `generate_content.py:518` — `consume_story_packet` (renders both boxscores)

**Commit:** `af4e7f5`.

---

### 4. Writers also need internet access — for facts the packet does not contain

**Failure mode.** Even with the boxscore in the packet, the writer wants to
reference biographical and contextual facts that aren't in any structured
source we provide (a player's college, hometown, prior team; a coach's
career history; league rules). Without web access, the writer falls back
on training-data fragments — which is precisely how the Iriafen draft-pick
detail leaked into the article without provenance in source.

**Fix.** The writer now also has `web_search_20250305` enabled, capped at
5 uses per article (most stat claims should resolve from the packet, so
search is for the bio/context edge cases). A `_SOURCE_HIERARCHY_RULE`
injected into the prompt enforces the order of preference:
1. Verified team context above
2. Story packet (boxscore, game_summary, standings_context)
3. `web_search` results, ESPN / league-official / team-official preferred

The model must cite the URL when stating a claim sourced from web_search.

**Where in code:**
- `generate_content.py:672` — `WRITER_MAX_WEB_SEARCHES = 5`
- `generate_content.py:674` — `_SOURCE_HIERARCHY_RULE`
- `generate_content.py:692` — `generate_article(game_summary, team, article_type, target_date)`

**Commit:** `af4e7f5`.

---

### 5. Forum-channel Discord posts can not have separate follow-up webhooks

**Failure mode.** First attempt at posting both the article AND the
fact-check report posted them as two separate webhook calls. Discord
returned `400` on the second call:
> "Webhooks posted to forum channels must have a thread_name or thread_id"
> (`code: 220001`)

The article landed but the detailed claim-by-claim breakdown didn't, so
reviewers saw a verdict color but had to dig through GH Actions artifacts
to see what was actually flagged.

**Fix.** Discord supports up to 10 embeds in a single webhook message.
Bundle the article embed + fact-check report embed into one POST. A new
`build_fact_check_embed(team, verdict, report)` helper returns the embed
dict so any poster can include it. The follow-up webhook function was
deleted.

**Where in code:**
- `generate_content.py:1025` — `build_fact_check_embed(team, verdict, report)`
- `generate_content.py:1044` — `post_recap_to_discord` (multi-embed payload)
- `scripts/demo_citron_feature.py` — `post_feature_to_discord` (same pattern)

**Commit:** `550de22`.

---

### 6. Verdict parsing must tolerate markdown decoration

**Failure mode.** The first end-to-end run with the new web-search-enabled
fact-checker produced a clean, correct FAIL report with detailed claim
citations. The Discord embed posted as UNKNOWN-colored, no follow-up
report attached. Reason: the model wrote `**VERDICT: FAIL**` with markdown
bold markers, and the parser checked
`line.strip().upper().startswith("VERDICT:")` — the leading `**` broke the
match. A working fact-checker was masked by a one-line parser bug.

**Fix.** Strip leading and trailing `*` decoration before matching. Eight
test cases now pin the behavior across plain text, markdown bold, mixed
asterisks, and intro-text-then-verdict shapes.

**Where in code:**
- `generate_content.py:923` — `_parse_verdict(report)`
- `scripts/codex_review.py:332` — `extract_verdict(review_text)`

**Commit:** `2f03530`.

---

### 7. GUARDRAILS belong in one place — drift across files is inevitable

**Failure mode.** A parallel session created `scripts/demo_citron_feature.py`
with the GUARDRAILS string copy-pasted inline plus a "KEEP IN SYNC" comment.
By the time the demo ran, the canonical GUARDRAILS in
`generate_content.generate_article` had grown a new BIOGRAPHICAL LOCKDOWN
clause; the demo's copy hadn't.

**Fix.** GUARDRAILS lifted to module-scope constant in `generate_content.py`.
Demos import it directly. The constant carries a comment that explicitly
forbids further duplication.

**Where in code:**
- `generate_content.py:640` — `GUARDRAILS` (module constant)
- `scripts/demo_citron_feature.py` — imports `GUARDRAILS` from generate_content

**Commit:** `cb656fd`.

---

### 8. Closed-set roster prevents off-roster player references

**Failure mode (anticipated, not yet observed live):** the writer could
plausibly invent teammates when describing rotations.

**Fix.** `kb_context_block` renders the full roster as a "Verified
{team_name} roster" section with explicit instructions:
> "reference ONLY these names when discussing your own team's players;
> opposing-team names from the game data are fine"

The roster is a closed set the model is told to obey. Per the Citron
fact-check, this guardrail is holding — every Mystics teammate named in the
article (Harmon, Amoore, Olsen, Iriafen) was on the verified roster.

**Where in code:**
- `generate_content.py:368` — `kb_context_block(kb)`

**Commit:** `1a60cdc`.

---

## Patterns to reuse when extending

- Any factual claim the writer might make where the inference is non-obvious
  → pre-compute it in `kb_context_block` and label it "Verified" in the
  prompt. See §1.
- Any per-game stat data → must be in the packet and rendered verbatim in
  `consume_story_packet`. See §3.
- Any new article-generation script → import `GUARDRAILS` from
  `generate_content`, never duplicate. See §7.
- Any new Discord poster → bundle related embeds in one webhook call. See §5.
- Any new fact-checker → enable web access and use the 4-tier verdict
  taxonomy. See §2.
- Any new verdict parser → strip markdown decoration before matching. See §6.

## Patterns NOT settled yet

These came up during the 2026-05-22 work but were deferred — they belong
in a future doc, not in this one as if they were resolved.

- **ESPN-sourced KB enrichment** (auto-refresh per-team bios, season
  aggregates, injury lists). Discussed; not built.
- **Packet ingestion for non-Mystics teams.** The current ingestion module
  is hardcoded for the Mystics. Extending to other teams (especially other
  sports) is real infrastructure work — see `docs/NEW_TEAM_CHECKLIST.md`.
- **Cost budgeting / per-call metering** for `web_search` use across the
  daily cron. No metering exists yet; the user runs against a finite
  Anthropic credit balance.
- **Article-level verdict semantics for ⚠️-only articles.** Current mapping
  treats "all ✅ + ⚠️" as PASS — fine for now, but worth revisiting if the
  process-discipline signal becomes important to surface.
