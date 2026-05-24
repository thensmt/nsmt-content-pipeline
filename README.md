# NSMT Content Pipeline

Automated sports article generator for thensmt.com.
Pulls DC/MD/VA game data, generates drafts with Claude Sonnet, runs an
adversarial fact-check via Codex (GPT-5 xhigh), and saves corrected drafts
to the NSMT admin backend for human review.

---

## How It Works

1. **GitHub Actions** runs daily at **10:00 UTC** (≈6 AM ET) via `daily-content.yml`
2. **Ingestion** builds a validated story packet from public sources (ESPN, WNBA.com, etc.) — `python -m ingestion.generate_story_packet`
3. **Writer (Sonnet 4.6, on CI)** drafts an article grounded on the packet + team KB
4. **Mac orchestrator** (`scripts/codex_rewrite.py`, run by launchd at 06:30 local) polls GH Actions for new drafts
5. **Codex fact-check v1** at xhigh runs on the Sonnet draft
6. If v1 != PASS → **Codex surgical rewrite** → **fact-check v2** on corrected body
7. **v2 PASS gate**: publish only triggers if v2 verdict is PASS (override with `--allow-v2-fail`)
8. **Publish workflow** (`publish-corrected.yml`) saves the article as `is_active=False` draft in admin and posts notification to Discord
9. **You review** the draft in [admin.thensmt.com](https://admin.thensmt.com/#/blogs), edit if needed, and toggle `is_active=True` to ship it
10. **React frontend** (thensmt.com) fetches active articles from the admin API

The pipeline saves directly to the existing NSMT admin backend — **no Contentful**, no separate CMS.

---

## Your Daily Workflow

1. Check `#recap-pipeline` (or per-team channels like `#commanders`) in Discord — the bot posts when a new draft is ready, including the v1→v2 verdict trail and corrections summary.
2. Open [admin.thensmt.com](https://admin.thensmt.com/#/blogs), find the draft (`is_active = false`)
3. Read it. Edit if needed. Toggle `is_active = true`. Done.
4. If v2 failed, the draft was blocked: check `data/blocked/{team}-{date}-{run_id}.md` for the review trail. Either fix the inputs and re-run, or push through with `python scripts/codex_rewrite.py --run-id <run_id> --allow-v2-fail`.

---

## Architecture (Hybrid CI ↔ Mac)

Codex CLI auth lives in `~/.codex/auth.json` (ChatGPT subscription) and cannot move to CI. So:
- **CI** owns: writing (Sonnet), publishing (admin POST), Discord posting. Holds all publish secrets.
- **Mac** owns: Codex fact-check + rewrite, publish trigger. Has Codex auth + `gh` CLI.

The Mac orchestrator is single-instance (fcntl lock on `.codex-rewrite.lock`) and Mac-side dedup tracks published `{team}-{type}-{date}` keys in `data/published_articles.json` to prevent duplicate admin POSTs on re-runs.

See `TURNOVER.md` for current state-of-play and `CODEX_ADVERSARIAL_REVIEW.md` / `FULL_REPO_ADVERSARIAL_REVIEW.md` for known limitations.

---

## Story Packet Ingestion

Builds a validated, public-source JSON packet for any team in `ALL_TEAMS`. Consumed by the writer prompt via `consume_story_packet()` in `generate_content.py`.

```bash
python -m ingestion.generate_story_packet --team mystics
python -m ingestion.generate_story_packet --team mystics --dry-run
python -m ingestion.generate_story_packet --team commanders --date 2026-05-23
```

Default output: `data/packets/{team}_{YYYY-MM-DD}.json`. Source responses cached under `cache/` with short per-source TTLs.

Generic ESPN fetcher (`ingestion/fetchers/espn_generic.py`) handles any team with an ESPN profile. Team-specific fetchers exist for fine-grained sources (e.g., `mystics_official.py`, `wnba_com.py`).

---

## Setup (One-Time)

### GitHub Secrets

| Name | Purpose |
|------|---------|
| `ANTHROPIC_API_KEY` | Claude Sonnet writer (CI) |
| `NSMT_USERNAME` | admin.thensmt.com login (Cognito auth) |
| `NSMT_PASSWORD` | admin.thensmt.com password |
| `DISCORD_PROXY_URL` | Cloudflare Worker URL for Discord posting |
| `DISCORD_PROXY_SECRET` | Shared secret for the Discord proxy |
| `DISCORD_COMMANDERS_WEBHOOK_URL` | Per-team direct webhook (optional, opt-in) |

### Local Mac Setup

```bash
cd ~/Downloads/Claude/NSMT/content-pipeline
python3 -m venv .venv
.venv/bin/pip install requests
codex login   # ChatGPT auth for fact-check/rewrite
gh auth login # GitHub CLI for workflow triggers
```

Optionally load the launchd job to auto-run the rewriter at 06:30 daily:
```bash
launchctl load -w scripts/com.thensmt.codex-rewrite.plist
```

### Manual Test Run

```bash
gh workflow run draft-baseline.yml -R thensmt/nsmt-content-pipeline -f team=commanders
sleep 90
.venv/bin/python scripts/codex_rewrite.py --since-hours 1 --wait-minutes 0
```

---

## Teams Covered

**Pro:** Commanders (NFL), Wizards (NBA), Capitals (NHL), Nationals (MLB),
Mystics (WNBA), Washington Spirit (NWSL), DC United (MLS), Capital City Go-Go (G-League)

**College:** Maryland Terrapins, Virginia Cavaliers, Virginia Tech Hokies, Georgetown Hoyas

---

## For Frontend Devs

See `FOR_QUINCY.md` — describes the admin API shape (`GET /blogs`) and the React rendering contract.
