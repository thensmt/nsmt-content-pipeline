# Session Turnover — 2026-05-22 / 2026-05-23

Last session: marathon ~7-hour pipeline build-out covering the Mystics demo eval,
multi-team data layer, Nationals MLB extension, 3-model comparison test, and
fact-check architecture decisions. This doc captures where to pick up next time.

---

## Final verdict on models (after tonight's empirical test)

| Use case | Model | Why |
|---|---|---|
| **Default writer (daily cron)** | **Claude Sonnet 4.6** | Best math + factual discipline. Got "through 52 games" right on the 3-model test when both Opus 4.7 and Haiku 4.5 incorrectly said "50 games." Mid-tier cost. Already the production setting. |
| **Premium / sponsor-facing longform** | Opus 4.7 | Best prose, strongest lede, most polished voice — but more factual errors at the claim level (10 ❌ vs Sonnet's 0 we could measure / Haiku's 7). Use selectively. ~5x Sonnet cost. |
| **Low-stakes / high-volume / rapid prototyping** | Haiku 4.5 | Cheapest, fastest. More vibes-y prose (more 💬 EDITORIAL flags). Acceptable for recaps where the packet's boxscore carries the factual weight. |
| **In-line fact-checker (when needed)** | Sonnet 4.6 + web_search | Same model writes and checks — that's fine because the writer prompt and fact-check prompt are different roles. |
| **Adversarial second-opinion fact-checker** | **Codex CLI (GPT-5 via your ChatGPT subscription)** | Free, runs locally, catches the same article-level verdicts as the in-line Sonnet check did on the 2-of-3 articles where we got Sonnet's verdict. |

## Final architecture (universal across teams)

This is how every team's articles get written in the production pipeline now:

```
                ┌──────────────────────────┐
                │   data/teams/{slug}.json │  ← timeless KB (roster,
                │       (per team)          │     coach, recent_games,
                └──────────┬───────────────┘     editorial_lessons)
                           │
                ┌──────────▼───────────────┐
                │ data/packets/{slug}_     │  ← per-game ESPN data
                │   {YYYY-MM-DD}.json      │     (boxscore, linescore,
                │       (per game-day)     │      top performers)
                └──────────┬───────────────┘
                           │
                ┌──────────▼───────────────┐
                │ Sonnet 4.6 + web_search  │  ← WRITER
                │  (max_uses=2)            │
                └──────────┬───────────────┘
                           │
              ┌────────────▼─────────────┐
              │  Discord #recap-pipeline │  ← article posts as
              │  + admin.thensmt.com     │     forum thread + admin draft
              │  (is_active=0)           │
              └────────────┬─────────────┘
                           │
              ┌────────────▼─────────────┐
              │  codex_review.py @       │  ← FACT-CHECK (Codex / GPT-5,
              │  8:05 AM ET launchd      │     uses ChatGPT subscription,
              │  (free)                  │     FREE, posts verdict reply
              └────────────┬─────────────┘     in the same thread)
                           │
              ┌────────────▼─────────────┐
              │  Human reviews + edits   │  ← you flip is_active=true
              │  in admin → publishes    │     when satisfied
              └──────────────────────────┘
```

**Optional in-line Sonnet fact-check** — toggled via env var `NSMT_FACT_CHECK=true`.
Default OFF (Codex covers it for free). Worth turning on only for individual
high-stakes runs where you need a verdict same-second on the Discord embed
rather than waiting for the 8:05 AM Codex pass. Saves ~$42-105/month at full
14-team daily cron capacity.

---

## What's on `origin/main` as of session end

Recent commits (newest first):
1. `<pending — final commit of session>` ARITHMETIC CONSISTENCY + NO COMPARISON WITHOUT SOURCE guardrails + NSMT_FACT_CHECK env toggle + fact_check_log.jsonl + this turnover doc
2. `5225c4d` web_search max_uses 5/10 → 2/2 (writer/fact-check) — eases free-tier TPM pressure
3. `5c3c74e` Comparison harness: longer cooldowns + drop FC embed to fix Discord 6000-char limit
4. `61bed65` 5-tier verdict + expanded sources + editorial_lessons + 3-model harness
5. `d78ad2c` Multi-team KB build-out: audit, refresh infra, unification, docs
6. `8d0b649` Generic per-sport ESPN packet ingestion (Nationals, future football/hockey)
7. `89182fe` Sport-specific terminology + MLB tenure guard

## Open decisions / not yet shipped

- **Add `editorial_lessons` entries** for the new errors caught in tonight's
  comparison run (Opus + Haiku both made the "50 games" + "season-high"
  errors). Universal versions of these ARE now in GUARDRAILS. Team-specific
  versions could still go in `data/teams/nationals.json:editorial_lessons`
  if you want a belt-and-suspenders approach.
- **Build out KBs for the 4 ESPN-gap teams** (DC Defenders roster, Marymount
  full KB, Mary Washington beyond current 15 players, Capital City Go-Go) —
  documented as gaps in their `verification_notes`.
- **Per-sport boxscore renderer** — the current `_format_boxscore_rows()` in
  `generate_content.py` is sport-neutral via the `entries` shape but does
  not group / label football's `passing` vs `rushing` vs `receiving`, hockey's
  `skaters` vs `goaltenders`, etc. with sport-aware section ordering. Defer
  until first football / hockey article is attempted.
- **Auto-extracted editorial_lessons** — currently lessons are manually added
  to KBs. A future feature: after each Codex review, a small Sonnet pass
  extracts lesson candidates and proposes appends to the team's KB. Doc'd
  in `docs/LESSONS_LEARNED.md` §11 as deferred.

## Open factual issues to revisit

- **Both Opus and Haiku wrote "50 games" for a 25-27 record** in tonight's
  comparison. The new ARITHMETIC CONSISTENCY guardrail (just shipped) should
  prevent this — verify next test run.
- **Both wrote "season-high strikeouts"** for Cavalli's 9 K. The NO
  COMPARISON WITHOUT SOURCE guardrail (just shipped) should prevent this —
  same verification next run.
- **All 3 model articles were rated FAIL** by both fact-checkers tonight.
  Not a fluke — the writers need tighter discipline. The new guardrails
  address the two most common failure modes; if articles still fail next
  test, the lessons system needs another round of additions.

---

## Cost watch

- **Started session:** roughly $3.50 Anthropic free credits
- **Major spends tonight:**
  - 3-model comparison runs (Opus + Sonnet + Haiku + retries): ~$1.50-2.00 total
  - Nationals end-to-end test: ~$0.09
  - Demo Citron runs: ~$0.30
- **Ended session:** roughly **$1.80** remaining
- **Rate limit context:** free tier has tight Sonnet TPM. 5-min cooldowns
  between heavy calls + max_uses=2 on web_search keeps things working but
  back-to-back Sonnet calls still occasionally 429. Top up $5+ for Tier 1
  (after 7-day wait) for ~2x TPM headroom.

## Daily cron cost (with current settings)

| Setting | Per article | 14 teams/day | Per month |
|---|---|---|---|
| Writer (Sonnet 4.6 + web_search max_uses=2) | ~$0.10-0.20 | $1.40-2.80 | $42-84 |
| In-line fact-check (Sonnet 4.6 + web_search max_uses=2), **DISABLED by default** | ~$0.10-0.25 | $0 (skipped) | $0 |
| Codex review (GPT-5 via ChatGPT subscription) | $0 | $0 | $0 |
| **Daily-cron Anthropic spend** | — | **$1.40-2.80** | **$42-84** |

Enable in-line fact-check per-run via `NSMT_FACT_CHECK=true` env var (set in
`workflow_dispatch` input `enable_fact_check`).

---

## Configurations to know

### Env vars (set in GH Actions secrets unless noted)
- `ANTHROPIC_API_KEY` — Sonnet writer + optional in-line fact-check
- `NSMT_USERNAME` / `NSMT_PASSWORD` — admin.thensmt.com Cognito auth
- `DISCORD_PROXY_URL` / `DISCORD_PROXY_SECRET` — Cloudflare Worker proxy for `#recap-pipeline`
- `NSMT_FACT_CHECK` — `true` to enable in-line Sonnet fact-check; default OFF

### Workflows
- `.github/workflows/daily-content.yml` — main daily cron (10 UTC, ~6 AM ET).
  workflow_dispatch inputs: `target_date`, `team_slug`, `enable_fact_check`
- `.github/workflows/kb-refresh.yml` — daily 07:00 UTC refresh of every team's
  KB from ESPN
- `.github/workflows/compare-models.yml` — manual 3-model comparison harness
- `.github/workflows/citron-feature-demo.yml` — manual one-off Citron feature
- `.github/workflows/mystics-season-demo.yml` — manual one-off season demo

### Local launchd job
- `~/Library/LaunchAgents/com.thensmt.codex-review.plist` — fires 8:05 AM ET daily.
  Polls Discord `#recap-pipeline` for unreviewed threads, runs Codex CLI fact-check
  on each, posts verdict reply.

### Key code paths
- `generate_content.py` — production writer + (optional) fact-check + Discord post
- `generate_content.GUARDRAILS` — module-level prompt constant, ~8 rules
- `generate_content._SOURCE_HIERARCHY_RULE` — authoritative sources list
- `ingestion/generate_story_packet.py:build_story_packet_for_team` — unified per-team packet path
- `ingestion/fetchers/espn_generic.py` — sport-agnostic ESPN fetcher
- `scripts/refresh_kb.py` — KB auto-refresh (daily cron)
- `scripts/codex_review.py` — Codex CLI second-opinion (8:05 AM launchd)
- `scripts/compare_models.py` — 3-model comparison harness
- `scripts/demo_citron_feature.py` — one-off player feature demo
- `data/teams/{slug}.json` — per-team KB (19 teams)
- `data/packets/{slug}_{date}.json` — per-game packets (runtime, gitignored)
- `data/fact_check_log.jsonl` — append-only fact-check log (gitignored)
- `docs/LESSONS_LEARNED.md` — 11 lessons captured from tonight's work
- `docs/NEW_TEAM_CHECKLIST.md` — onboarding new teams

---

## Next pickup — suggested order

1. **Trigger one daily-cron-style run with NEW guardrails** to verify the
   ARITHMETIC CONSISTENCY + NO COMPARISON WITHOUT SOURCE rules actually
   prevent the "50 games" / "season-high" failures from tonight. One team,
   one date: `gh workflow run "NSMT Daily Content Generation" -f team_slug=nationals -f target_date=2026-05-21`.
   Cost: ~$0.10-0.20.
2. **Read the article + verdict in Discord**, confirm clean. If still
   fails on the new error patterns, those guardrails need stronger
   language (or move to a `editorial_lessons` per-team).
3. **Decide on permanent in-line fact-check policy** — either:
   - Keep default OFF (Codex-only) → save $42-84/month
   - Re-enable with `NSMT_FACT_CHECK=true` permanently → ~$42-105/month for
     same-second verdict on the Discord embed
4. **Update `LESSONS_LEARNED.md` §10/§11** with tonight's empirical findings
   on the 3-model comparison: Codex agreement with Sonnet, Haiku producing
   FEWER errors but MORE editorial flags, Opus's prose quality vs accuracy
   trade-off.
5. **Build out the 4 ESPN-gap KBs** (Defenders, Marymount, Mary Washington
   expansion, Go-Go) when ready to write articles for those teams.
6. **Run the comparison harness** (or revisit the deferred Opus
   second-opinion if you want to compare Codex vs Sonnet at the claim level)
   — requires reading both fact-check reports side-by-side from the same
   Discord thread.

## What NOT to do tomorrow (decisions already made)

- Don't re-introduce the legacy Mystics fetcher path. Mystics is on the
  generic path now alongside every other team.
- Don't trust TEAMS dict `espn_id` values without checking against
  `/sports/{sport}/{league_slug}/teams`. Four were wrong before tonight.
- Don't duplicate `GUARDRAILS` into a new demo script — import it.
- Don't post fact-check report and article as two separate Discord embeds
  in the same message; Discord enforces a 6000-char combined limit.

---

## Quick reference: relevant commands

```bash
# Trigger a single-team article generation (cheap, ~$0.10-0.20)
gh workflow run "NSMT Daily Content Generation" \
  -f team_slug=nationals -f target_date=2026-05-21

# Enable in-line fact-check for one run (~adds $0.10-0.25)
gh workflow run "NSMT Daily Content Generation" \
  -f team_slug=nationals -f enable_fact_check=true

# Refresh all team KBs from ESPN ($0 — pure HTTP)
gh workflow run "KB Refresh (ESPN)"

# Single-model comparison (e.g., Sonnet only)
gh workflow run "3-Model Comparison (Nationals season feature)" -f models=sonnet

# Run Codex review on any pending Discord threads (FREE)
python scripts/codex_review.py --since-hours 1 --wait-minutes 0

# Inspect the fact-check log
cat data/fact_check_log.jsonl | jq .
```

---

Last updated: 2026-05-23 — end of marathon session covering Mystics demo eval through
3-model Nationals comparison and the universal fact-check architecture decision.
