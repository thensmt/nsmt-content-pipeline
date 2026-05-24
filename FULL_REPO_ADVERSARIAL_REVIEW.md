# FULL_REPO_ADVERSARIAL_REVIEW.md

## Runtime context

- Repo: `/Users/david/Downloads/Claude/NSMT/content-pipeline`
- Review date: 2026-05-23
- Scope: complete repo pass, excluding re-litigation of the already-covered architecture and X plan findings unless new evidence confirms or worsens them.
- Test command run:
  - `.venv/bin/python -m unittest discover -s tests -v` passes 3 story-packet tests.
  - `.venv/bin/python -m unittest discover -v` fails because root `test_discord.py` executes side effects at import time.

## Findings (P0-P5)

### P0 — `mystics-season-demo.yml` is a dead workflow that cannot run
- `.github/workflows/mystics-season-demo.yml:40-42` invokes `python scripts/demo_mystics_season.py`.
- `scripts/` contains no `demo_mystics_season.py`; `ls scripts` shows only `codex_review.py`, `codex_rewrite.py`, `compare_models.py`, `demo_citron_feature.py`, `publish_from_corrected.py`, and `refresh_kb.py`.
- `TURNOVER.md:154` still describes this as a manual one-off season demo.
- `docs/LESSONS_LEARNED.md:17` cites the same missing script as part of the historical Mystics demo path.
- This is not harmless doc rot. It is a clickable GitHub Action wired to production secrets (`ANTHROPIC_API_KEY`, `DISCORD_PROXY_URL`, `DISCORD_PROXY_SECRET`) at `.github/workflows/mystics-season-demo.yml:33-37` that fails immediately if used.

### P0 — Root `test_discord.py` makes default unittest discovery unsafe
- `test_discord.py:41-47` calls `post_recap_to_discord()` at module import time.
- `test_discord.py:57` raises `SystemExit(1)` when Discord env vars are absent.
- Running `.venv/bin/python -m unittest discover -v` imports it as a test module and fails before the real test suite completes.
- The only clean command is `.venv/bin/python -m unittest discover -s tests -v`.
- This proves there is no robust default test entry point. A maintainer running normal discovery gets a false failure or, with secrets present, may post a live Discord test thread.

### P1 — Ingestion is now production-shaped, but its tests still cover only the deprecated Mystics path
- `ingestion/generate_story_packet.py:10-16` says `build_story_packet()` is legacy and kept only for `tests/test_story_packet.py`.
- `ingestion/generate_story_packet.py:145-217` defines the generic production builder used by CLI for every team.
- `tests/test_story_packet.py:101-178` imports and tests only `build_story_packet`, not `build_story_packet_for_team`.
- `daily-content.yml:54-55` runs the generic CLI before writing.
- Result: the path currently used by CI for packet generation has no unit coverage. The covered path is explicitly deprecated.

### P1 — Daily content silently falls back when packet generation fails
- `.github/workflows/daily-content.yml:54-55` runs `python -m ingestion.generate_story_packet ... || echo "Packet generation failed ... writer will fall back to web_search."`
- That makes ingestion failure non-fatal even though the packet is the grounding layer intended to prevent stat hallucinations.
- The article writer then proceeds with `generate_content.py:886-887`, where packet loading returns an empty block if no packet exists.
- This turns a data-foundation failure into a normal writer run. The user may only see a line in Actions logs.

### P1 — Story packet validation does not validate boxscore contracts
- `ingestion/schema.py:131-135` defines optional `boxscore` and `opponent_boxscore`.
- `ingestion/validators.py:56-145` validates required outer fields and lists, but never validates `boxscore`, `opponent_boxscore`, `entries`, `rows`, or stat labels.
- `generate_content.py:728-737` renders boxscore rows as authoritative prompt data.
- If ESPN shape changes or a fetcher emits malformed boxscore entries, validation still passes and the writer gets bad "verbatim" source material.

### P1 — State files are split between ignored and unignored, and one is currently untracked
- `.gitignore:9` ignores `.codex-review-state.json`.
- `.gitignore` does not ignore `.codex-rewrite-state.json`.
- `.codex-rewrite-state.json:2-6` contains processed GitHub Actions run IDs.
- `git status --short` shows `?? .codex-rewrite-state.json`.
- This is exactly the kind of local run-state that should not enter git history. It also creates duplicate-publish risk if cloned elsewhere or lost.

### P1 — Launchd jobs can overlap the old and new review/publish paths
- `scripts/com.thensmt.codex-rewrite.plist:32-46` runs at 06:30 and 07:30, each process polling up to 90 minutes by default (`scripts/codex_rewrite.py:419-421`).
- That means the 06:30 process can still be alive when 07:30 starts.
- Both processes read the same JSON state file (`scripts/codex_rewrite.py:47`, `:81-92`) with no file lock.
- Both enumerate pending runs and mark processed only after `process_run()` returns (`scripts/codex_rewrite.py:453-464`).
- If both launchd instances see the same pending run before either saves state, they can both trigger `publish-corrected.yml`.
- This compounds the already-known non-idempotent admin POST problem.

### P1 — `publish_from_corrected.py` treats Discord failure as non-fatal after admin save
- Baseline path saves admin first at `scripts/publish_from_corrected.py:179`, then posts Discord at `:184-197`.
- Discord failure is caught and logged as "non-fatal" at `scripts/publish_from_corrected.py:198-199`.
- Recap path does the same at `scripts/publish_from_corrected.py:203-227`.
- There is no retry, ledger, alert, or failure state. The admin draft can exist with no Discord notification and no reviewer-visible signal except CI logs.

### P1 — `generate_content.py` has become a kitchen-sink module with production secrets, teams, ingestion rendering, writer prompt, fact-checking, admin auth, and Discord posting
- Credentials and constants live at `generate_content.py:27-40`.
- Team registry lives in the same module (`generate_content.py:172` for `ALL_TEAMS`).
- KB and packet loading live at `generate_content.py:281-308`.
- Prompt rendering and guardrails live at `generate_content.py:658-919`.
- Fact-checking lives at `generate_content.py:1019-1122`.
- Cognito/admin POST lives at `generate_content.py:1190-1248`.
- Discord posting lives at `generate_content.py:1285-1358`.
- `generate_baselines.py:35-55`, `scripts/compare_models.py:70-89`, `scripts/demo_citron_feature.py:60-75`, `scripts/publish_from_corrected.py:37-53`, `scripts/codex_review.py:73-77`, and `scripts/codex_rewrite.py:73-74` all import internals from it.
- This is brittle cross-file coupling masquerading as reuse.

### P2 — Scheduled workflows are only two, but one writes to repo every day
- Scheduled workflows:
  - `.github/workflows/kb-refresh.yml:8-10` runs daily at 07:00 UTC.
  - `.github/workflows/daily-content.yml:3-8` runs daily at 10:00 UTC.
- `kb-refresh.yml:26-27` has `contents: write`.
- `kb-refresh.yml:62-73` commits and pushes changes to `data/teams/`.
- `scripts/refresh_kb.py:160-175` mutates JSON files when any refreshable field changes.
- This is an active production data writer, not a harmless refresh. There is no test gate before committing changed KBs.

### P2 — Demo workflows are manual, but still wired to production spend and posting
- `citron-feature-demo.yml:3-13` is manual only, but `:31-46` runs a real Anthropic generation/fact-check and Discord post unless flags disable them.
- `compare-models.yml:3-21` is manual only, but `:48-71` runs up to three paid model calls plus fact-checks and posts unless `no_discord=true`.
- `mystics-season-demo.yml` is manual but broken and secret-wired.
- These are not burning scheduled Actions minutes, but they remain easy-to-trigger production-cost workflows.

### P2 — `compare-models.yml` can exceed its 25-minute timeout by design
- `.github/workflows/compare-models.yml:26` sets `timeout-minutes: 25`.
- `scripts/compare_models.py:117-125` defines 60s intra-model and 300s inter-model cooldowns.
- Default models are three (`scripts/compare_models.py:448`), and each model can do a writer call, 60s sleep, fact-check call, Discord post, and 300s sleep before the next.
- The workflow default date/model combo is a long-running bake-off but has a tight timeout. It is unstable as a repeatable harness.

### P2 — Root docs actively contradict current production behavior
- `README.md:4` says drafts save to Contentful.
- `README.md:21-24` tells the user to review and publish in Contentful.
- `README.md:64-72` tells the user to add Contentful secrets and run `setup_contentful.py`.
- `FOR_QUINCY.md:5` says "we are NOT using Contentful" and the pipeline pushes directly to the existing admin backend.
- `generate_content.py:1216-1248` confirms actual production uses `POST /admin/blogs`, not Contentful.
- A new operator following README will set up the wrong CMS.

### P2 — `setup_contentful.py` is abandoned but executable
- `setup_contentful.py:1-4` says it creates a Contentful Article content type.
- `setup_contentful.py:10-18` defaults a real Contentful space ID and exits only if no token is present.
- `FOR_QUINCY.md:5` says Contentful is no longer used.
- `README.md:68-72` still instructs running this script.
- This should be deleted or quarantined under `archive/` with an explicit "obsolete" header.

### P2 — Docs about ingestion are stale against the current generic ESPN path
- `README.md:31-33` says ingestion is not wired into `generate_content.py` yet.
- `generate_content.py:867-887` says `generate_article()` loads same-date story packets and injects them into prompts.
- `README.md:51-53` says status is Mystics only and consumer hookup is deferred.
- `ingestion/generate_story_packet.py:145-217` implements a generic builder for any team in `ALL_TEAMS`.
- `docs/NEW_TEAM_CHECKLIST.md:52-86` still frames packet ingestion as Mystics-only and suggests generalizing/copying the old hardcoded `espn.py`, while the generic `espn_generic.py` already exists.

### P2 — Cognito `USER_PASSWORD_AUTH` keeps a standing admin password in CI
- `generate_content.py:28-30` reads `NSMT_USERNAME` and `NSMT_PASSWORD`.
- `generate_content.py:1190-1213` uses Cognito `InitiateAuth` with `AuthFlow: USER_PASSWORD_AUTH`.
- `daily-content.yml:59-63` injects the admin username/password into CI.
- `publish-corrected.yml:94-99` does the same.
- This works, but it is a broad standing credential. For automation, a narrower machine-to-machine token, service role, or admin API key with scoped permissions would be cleaner than a human-style password auth flow.

### P2 — `.env` is gitignored but scripts auto-load it and root currently contains Discord bot credentials
- `.gitignore:5` ignores `.env`.
- Local `.env` contains `DISCORD_BOT_TOKEN` and `GUILD_ID` keys.
- `scripts/codex_review.py:53-71`, `scripts/codex_rewrite.py:53-71`, `scripts/compare_models.py:52-67`, and `scripts/demo_citron_feature.py:36-58` auto-load root `.env`.
- The values are not tracked, but the pattern increases blast radius: many scripts import and hydrate local secrets before deciding what they need.

### P2 — `codex_review.py` marks reviewed only after all processing, with no durable in-progress state
- `scripts/codex_review.py:427-428` loads reviewed IDs.
- `scripts/codex_review.py:457-469` processes threads and writes state at the end.
- If it posts a review reply and crashes before saving state, the same thread can be reviewed again on the next run.
- This is a less severe version of the rewrite duplicate problem, but still noisy and avoidable.

### P2 — `codex_rewrite.py` has no in-progress lock
- `scripts/codex_rewrite.py:431` loads processed run IDs.
- `scripts/codex_rewrite.py:453-464` lists pending, processes, then marks processed.
- No state transition exists for "processing."
- No file lock exists around `.codex-rewrite-state.json`.
- Two processes or manual invocations can race.

### P2 — Admin POST is blind create in both recap and baseline paths
- `generate_content.py:1222-1243` posts to `/admin/blogs` with slug but does not check for existing slug.
- `generate_baselines.py:231-253` does the same.
- `scripts/publish_from_corrected.py:176-183` calls the baseline save path.
- This carries forward the duplicate-draft incident from prior reviews and appears in multiple paths.

### P3 — KB refresh can silently skip bad fetches and still report a successful workflow
- `scripts/refresh_kb.py:184-193` catches fetch failures and returns `None`.
- `scripts/refresh_kb.py:90-158` simply skips fields when `info`, `roster_payload`, or `sched_payload` is absent.
- `scripts/refresh_kb.py:373-407` prints statuses and always returns `0`.
- `.github/workflows/kb-refresh.yml:44-60` treats that as a successful refresh.
- An ESPN outage or API shape change may produce no changes and still look green unless someone reads logs.

### P3 — Source cache writes are not atomic
- `ingestion/cache.py:75-80` fetches data and writes JSON directly to the final cache path.
- There is no temp-file-and-rename.
- Concurrent packet generation can leave partial JSON; later reads catch invalid JSON at `ingestion/cache.py:66-73`, but that just causes refetching. Low severity, but this is still fragile shared state.

### P3 — Robots handling defaults to allow on failure
- `ingestion/cache.py:98-108` defaults to `allow_all=True` if `robots.txt` fetch fails.
- `ingestion/cache.py:112-115` also defaults allow on non-200.
- This is pragmatic, but it means "respect robots.txt" is softer than the docs imply. If a site blocks robots fetches, the fetcher proceeds.

### P3 — Official-site scraping is brittle HTML parsing
- `ingestion/fetchers/mystics_official.py:65-92` uses a minimal custom anchor parser.
- `ingestion/fetchers/mystics_official.py:94-123` filters by link title length, href domain, and `/news`.
- `ingestion/fetchers/mystics_official.py:126-145` tries to find dates by scanning 300 visible-text chars after the title.
- Any WNBA site redesign can silently yield no parsed stories, producing only a confidence note.

### P3 — WNBA standings and injury parsing are regex/scrape fragile
- `ingestion/fetchers/wnba_com.py:234-247` parses standings from visible text with one regex for `WAS`.
- `ingestion/fetchers/wnba_com.py:250+` fetches the injury report as HTML.
- This is acceptable as enrichment, but it should not be treated as hard source-of-truth without tests around fixture HTML.

### P3 — Season aggregator exists but has no visible caller
- `ingestion/season_aggregator.py:24-96` implements a full ESPN season aggregate.
- `rg` shows no production caller in workflows or scripts.
- It may be useful future work, but today it is untested surface area.
- If kept, it needs either a documented entry point or tests. Otherwise it is a drift magnet.

### P3 — `compare_models.py` is a one-off harness but remains production-adjacent
- `scripts/compare_models.py:1-32` identifies itself as a three-model comparison harness.
- `TURNOVER.md:152` says workflow is manual.
- `scripts/compare_models.py:402-405` posts to Discord by default.
- This is not dead, but it is experimental and should be clearly labeled as such in workflow names and docs.

### P3 — Citron demo is not dead, but it is a one-off path with production posting defaults
- `scripts/demo_citron_feature.py:2-18` calls it a one-off demo.
- `citron-feature-demo.yml:31-46` wires it to GitHub Actions.
- `scripts/demo_citron_feature.py:320-324` posts to Discord unless `--no-discord` is set.
- Keep it if useful, but label it "manual / experimental / costs money / posts to Discord."

### P3 — `test_discord.py` belongs under `scripts/` or must be guarded
- `test_discord.py:1-15` describes itself as a standalone verification script.
- Because its filename starts with `test_`, unittest discovers it.
- It should be renamed to `scripts/test_discord_post.py`, or wrapped in `if __name__ == "__main__":`.

### P3 — `generate_baselines.py` comment says max_tokens for 700-900 words while prompt asks 500-600
- `generate_baselines.py:114` and `:136` prompt for 500-600 words.
- `generate_baselines.py:177` comments `2048` max tokens as "700-900 words."
- Minor, but it reflects prompt churn and makes cost/length reasoning unreliable.

### P3 — README schedule is wrong
- `README.md:10` says GitHub Actions runs every morning at 8am ET.
- `.github/workflows/daily-content.yml:4-8` schedules 10:00 UTC, commented as 6am EDT / 5am EST with typical delay to 7-9am ET.
- `TURNOVER.md:148` correctly describes 10 UTC / ~6 AM ET.
- The main README should not be the stale one.

## What prior reviewers missed

- The "ingestion layer" is no longer just Mystics MVP in practice. CI now calls the generic packet generator, but tests still cover the old Mystics-only function.
- A live GitHub workflow invokes a missing script: `mystics-season-demo.yml` cannot run.
- Default test discovery is broken by root `test_discord.py`, which performs live Discord behavior at import time.
- `.codex-rewrite-state.json` is not gitignored and is currently untracked local state containing processed run IDs.
- The rewrite launchd schedule can overlap itself because the 06:30 and 07:30 windows each run a 90-minute poller with no lock.
- Root docs are not merely stale; README tells operators to use Contentful while the actual production pipeline posts to the NSMT admin API.
- `setup_contentful.py` is abandoned but still present and still referenced by README.
- `kb-refresh.yml` is a scheduled repo-writing production job with no tests or failure gating beyond log output.
- `compare-models.yml`, `citron-feature-demo.yml`, and `mystics-season-demo.yml` are manual only, so they are not burning scheduled minutes, but they are still production-secret and production-posting surfaces.
- Validation does not cover the authoritative boxscore fields that downstream prompts tell the model to trust verbatim.

## Unresolved from prior stages

- v2 verdict still does not gate publish: `scripts/codex_rewrite.py:347-349` records v2, then `scripts/codex_rewrite.py:399-411` triggers publish regardless.
- `publish-corrected.yml` still uses `workflow_dispatch` inputs as document transport for full article body and review trail (`.github/workflows/publish-corrected.yml:35-53`, `:77-82`).
- Admin draft creation is still non-idempotent in both `generate_content.py:1222-1243` and `generate_baselines.py:231-253`.
- X plan still has the Mac-local ledger vs CI cron contradiction (`X_INTEGRATION_PLAN.md:39-45`, `:52`, `:96`).
- Prompt rules are still accumulating as policy debt (`style_guide.py:23-71`, `generate_content.py:780-826`, `generate_baselines.py:79-151`).
- Discord still shapes article length because full article bodies are embedded (`generate_content.py:1305-1309`, `scripts/publish_from_corrected.py:89-101`).

## Most critical issue

The highest-impact repo-wide issue is **state and idempotency are still fake**.

This shows up everywhere:
- Local JSON state, not a ledger.
- No in-progress locks.
- Launchd overlap possible.
- Admin POST is blind create.
- v2 FAIL still publishes.
- Discord failure after admin save is non-fatal and untracked.
- Packet generation failure is downgraded to "writer will fall back."

The repo has many review and verification surfaces, but no durable state machine that makes those surfaces authoritative. Until there is one idempotent article lifecycle keyed by stable article ID, every subsystem is compensating with logs, prompts, and hope.

## Prompt for next tool / session

Start by cleaning operational correctness, not features:

1. Add `.codex-rewrite-state.json` to `.gitignore`.
2. Rename or guard `test_discord.py` so default test discovery is safe.
3. Delete or disable `mystics-season-demo.yml`, or restore `scripts/demo_mystics_season.py`.
4. Add a lock / in-progress state to `codex_rewrite.py`, or remove overlapping launchd windows.
5. Enforce `v2_verdict == PASS` before triggering publish.
6. Add idempotency before admin POST: stable `article_id`, preflight lookup or admin upsert support.
7. Update README to reflect admin backend, not Contentful; move `setup_contentful.py` to archive or delete it.
8. Add tests for `build_story_packet_for_team`, `espn_generic`, `publish_from_corrected` failure behavior, and `codex_rewrite` publish gating.

Do not add X, more demo workflows, or more prompt rules until this is done.
