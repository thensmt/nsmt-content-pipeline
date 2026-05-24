# NEXT_STEPS.md — Where to Pick Up

Last updated: 2026-05-23 (end of marathon cleanup session)

Reads the full history of decisions in:
- `TURNOVER.md` — last session's state
- `CODEX_ADVERSARIAL_REVIEW.md` — first adversarial pass (pipeline architecture)
- `X_INTEGRATION_PLAN.md` — proposed X integration (has a P0 bug, see X review)
- `X_PLAN_ADVERSARIAL_REVIEW.md` — adversarial review of X plan
- `FULL_REPO_ADVERSARIAL_REVIEW.md` — full repo adversarial pass (this is the master finding list)

This file captures what's left after the cleanup session executed against FULL_REPO_ADVERSARIAL_REVIEW.md.

---

## ✅ Shipped in this session

| Severity | Fix | Files touched |
|---|---|---|
| P0 | Deleted dead `mystics-season-demo.yml` workflow | `.github/workflows/mystics-season-demo.yml` (deleted) |
| P0 | Guarded `test_discord.py` from `unittest discover` | `test_discord.py` |
| P1 | Gitignored `.codex-rewrite-state.json`, `.codex-rewrite.lock`, `data/published_articles.json`, `data/blocked/` | `.gitignore` |
| P1 | Added fcntl lock to `codex_rewrite.py` (prevents launchd + manual race) | `scripts/codex_rewrite.py` |
| P1 | Collapsed launchd plist 06:30+07:30 → single 06:30 window, 120-min poll | `scripts/com.thensmt.codex-rewrite.plist` |
| P1 | Enforced v2 PASS gate (blocks publish on v2 != PASS, `--allow-v2-fail` override) | `scripts/codex_rewrite.py` |
| P1 | Added Mac-side dedup (`data/published_articles.json`) — skips republish of same `{team}-{type}-{date}` | `scripts/codex_rewrite.py` |
| P1 | Discord-failure surfaces as exit-5 (workflow fails, GH email fires) — admin draft preserved | `scripts/publish_from_corrected.py` |
| P1 | `daily-content.yml` packet failure now uses `::warning` annotation + tags run (`PACKET_STATUS`) instead of silent `echo` | `.github/workflows/daily-content.yml` |
| P1 | Boxscore validation added to `validators.py` — rejects malformed entries/rows | `ingestion/validators.py` |
| P1 | `kb-refresh.yml` now runs unit tests before commit (gates auto-push) | `.github/workflows/kb-refresh.yml` |
| P1 | New tests for `build_story_packet_for_team` + `espn_generic` internals (6 new tests, 9 total passing) | `tests/test_story_packet_for_team.py` |
| P2 | README rewritten to match production (admin API, hybrid CI↔Mac, v2 gate); old Contentful sections removed | `README.md` |
| P2 | `setup_contentful.py` moved to `archive/` + guarded with `raise SystemExit` | `archive/setup_contentful.py` |
| P3 | Stale `max_tokens` comment fixed (2048 → 1536, matches 500-600 word prompts) | `generate_baselines.py:177` |

After this session: tests are 9/9 passing under default `unittest discover`. Workflow inventory is 5 (was 7 — `mystics-season-demo.yml` deleted; X-related workflows never built).

---

## 🟡 Deferred — needs design or coordination

### D1. `generate_content.py` kitchen-sink split (P1, deferred)

**Why deferred:** `generate_content.py` is ~1,400 lines and imported by 6+ files via internals (`ALL_TEAMS`, `CATEGORY_IDS`, `load_team_kb`, `consume_story_packet`, `get_nsmt_token`, etc.). A safe split needs:
1. A target module map agreed up front (e.g., `teams.py`, `kb.py`, `admin_client.py`, `discord_client.py`, `prompts/recap.py`, `prompts/preview.py`)
2. Each move done in its own commit so imports can be migrated incrementally
3. Test coverage for the moved code BEFORE the move (currently zero coverage for most of it)

Shipping this without the above is high-risk for breaking the daily cron silently.

**Recommended sequence when picked up:**
1. Sketch the module map (30 min — call it `REFACTOR_PLAN.md`)
2. Add minimal tests for `get_nsmt_token`, `post_recap_to_discord`, `consume_story_packet`, `CATEGORY_IDS` (~2 hr)
3. Extract one module at a time, fix imports across the 6+ callers, run full test suite + manual smoke on Commanders
4. Estimated total: 6-8 hours across 2-3 sessions

### D2. Cognito `USER_PASSWORD_AUTH` → scoped service token (P2, blocked)

**Why blocked:** The admin backend (`https://rjl5qaqz7k.execute-api.us-east-1.amazonaws.com/prod`) currently only supports the user-password auth flow. Moving to a narrower machine-to-machine token requires the admin team to:
1. Add a service-account / API-key auth path
2. Define scoped permissions (write blogs, no user management, no read of other users' data)
3. Rotate David's personal admin password out of CI secrets

**Recommended sequence when picked up:**
1. Ask the admin team for a scoped service token capable of `POST /admin/blogs` and nothing else
2. Once issued, store as `NSMT_SERVICE_TOKEN` in GH Secrets
3. Update `generate_content.get_nsmt_token()` to prefer the service token, falling back to USER_PASSWORD_AUTH only if `NSMT_SERVICE_TOKEN` is unset
4. After verifying a clean cron run, rotate David's admin password and remove `NSMT_USERNAME` / `NSMT_PASSWORD` from CI

This change can't move forward unilaterally — admin backend work is the gate.

---

## 🚫 Out of scope tonight (user explicitly deferred)

### X Integration (all X-related work)

Status as of session end:
- `X_INTEGRATION_PLAN.md` — proposal exists. **Has a P0 architectural bug** (state-ownership contradiction) that needs to be resolved before any code is written.
- `X_PLAN_ADVERSARIAL_REVIEW.md` — full review of the plan. Recommends choosing between:
  - **(a) Zapier/Make/RSS-driven auto-tweet** — fast, low code, reversible
  - **(b) Mac-owned (launchd) full pipeline** — laptop uptime is now a production dep
  - **(c) CI-owned with REMOTE ledger** (Turso/Supabase/D1) — correct architecture, more setup
- Pre-X work that should land first (now mostly done): v2 PASS gate ✅, admin POST idempotency ✅, stable article_id ✅

Resume X work fresh tomorrow per user request.

---

## 🟢 Still-known limitations to consider over time

These were flagged in the adversarial reviews but are lower-priority or design-pending:

- **`generate_content.py` is a kitchen-sink module** (see D1 above)
- **`workflow_dispatch` as document transport** in `publish-corrected.yml` — full body + review_trail passed as string inputs. Will hit GH's 65k char input cap eventually. Replace with artifact upload + URL.
- **Cognito `USER_PASSWORD_AUTH`** (see D2 above)
- **Ingestion HTML scrapers are fragile** (`mystics_official.py`, `wnba_com.py` regex/anchor parsing). When sites redesign, packets silently empty. The new boxscore validator catches *malformed* data; doesn't catch *missing* data.
- **No retry queue for failed publishes.** Discord failures now exit non-zero (good), but you still have to manually re-trigger.
- **`compare-models.yml` and `citron-feature-demo.yml`** are manual one-off experimental workflows wired to production spend + posting. Should rename to `experimental-*` or move to a dedicated branch.

---

## ⏯ Resume command for tomorrow morning

```bash
cd ~/Downloads/Claude/NSMT/content-pipeline
git status
git diff
.venv/bin/python -m unittest discover -v   # should be 9/9 OK
```

Then pick: (a) commit + push the cleanup, OR (b) start fresh on X integration with the architecture decision from `X_PLAN_ADVERSARIAL_REVIEW.md`.
