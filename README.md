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

## Mystics Postgame Recap MVP

Additive prototype for Washington Mystics postgame drafting:

```bash
python -m ingestion.mystics_postgame_recap --as-of 2026-05-24
python -m ingestion.mystics_postgame_recap --fixture tests/fixtures/espn_mystics_postgame_401856918.json
python -m ingestion.mystics_postgame_recap --fixture tests/fixtures/espn_mystics_postgame_401856918.json --dry-run
python -m ingestion.mystics_postgame_recap --fixture tests/fixtures/espn_mystics_postgame_401856918.json --discord-review
python -m ingestion.mystics_postgame_recap --fixture tests/fixtures/espn_mystics_postgame_401856918.json --generate-assets
python -m ingestion.mystics_postgame_recap --fixture tests/fixtures/espn_mystics_postgame_401856918.json --qa
python -m ingestion.mystics_postgame_recap --fixture tests/fixtures/espn_mystics_postgame_401856918.json --generate-assets --qa --discord-review
python -m ingestion.mystics_postgame_recap --fixture tests/fixtures/espn_mystics_postgame_401856918.json --generate-assets --qa --external-editor-packet
python -m ingestion.mystics_postgame_recap --fixture tests/fixtures/espn_mystics_postgame_401856918.json --ingest-external-editor-response tests/fixtures/claude_external_editor_response_401856918.json
python3 -m unittest discover -s tests -v
```

The stable CLI entrypoint is `ingestion/mystics_postgame_recap.py`. It
orchestrates focused modules for ESPN fetch/fixture loading
(`ingestion/espn_mystics.py`), packet normalization
(`ingestion/mystics_normalizer.py`), memory and story angle handling
(`newsroom/memory.py`, `newsroom/story_angles.py`), draft/assets/QA generation
(`newsroom/drafts.py`, `newsroom/assets.py`, `newsroom/qa.py`), and local review
handoffs (`newsroom/external_review.py`, `newsroom/discord_review.py`).
Artifact validation boundaries live in `newsroom/schemas.py`. The
pipeline finds the most recent completed game, normalizes it to
`data/packets/mystics_postgame_{event_id}.json`, extracts recap signals, and
writes a Maya Brooks markdown draft to `drafts/mystics/`. It does not publish or
call the admin API.

Maya Brooks' persistent editorial memory lives in `data/memory/mystics/`:

- `season_narratives.json` — conservative season-level framing prompts
- `player_profiles.json` — player-specific editorial lenses, not bio claims
- `recent_storylines.json` — reusable storyline prompts for angle selection
- `editorial_rules.json` — hard limits such as no invented quotes, injuries, or locker-room details

The recap packet attaches those memory files under `memory` and creates exactly
three ranked `story_angles`. The markdown draft uses the top-ranked angle and
adds an `Editorial Notes` section with the selected angle, alternate angles,
supporting signals, risk flags, ESPN event ID, and generated timestamp.

Use `--discord-review` to generate a Discord-ready review package without
posting it. Review JSON files are saved to `drafts/mystics/review/` as:

```text
drafts/mystics/review/mystics-postgame-{YYYY-MM-DD}-{event_id}-review.json
```

Editors should check `thread_title`, `summary_message`, `selected_angle`,
`alternate_angles`, `risk_flags`, `article_markdown_path`, `packet_path`, and
`editor_checklist`. The review package is only a handoff artifact for a future
bot/manual post. If `--qa` is also used, the review package includes
`qa_report_path`, `overall_recommendation`, `lowest_scoring_items`, and
`top_issue_flags`. If an external editor packet exists, it includes
`external_editor_packet_path` and `recommended_external_review`. It does not
call Discord, Contentful, or the NSMT admin API. If an external editor decision
summary exists, it also includes the verdict, confidence, blocker count,
revision flag, and mandatory human-editor flag.

Use `--generate-assets` to create secondary editorial assets from the same
normalized packet and the top-ranked story angle. Asset files are saved under:

```text
drafts/mystics/assets/
```

Generated assets include:

- `mystics-short-recap-{event_id}.md` — 120-180 word fast postgame recap
- `mystics-takeaways-{event_id}.md` — exactly three title/explanation takeaways
- `mystics-push-alert-{event_id}.txt` — max-160-character push alert
- `mystics-newsletter-blurb-{event_id}.md` — conversational newsletter tease
- `mystics-seo-summary-{event_id}.md` — one-paragraph readable SEO summary
- `mystics-social-{event_id}.txt` — Instagram/X-compatible caption with final score
- `mystics-headlines-{event_id}.json` — exactly five ranked headline candidates with tone, confidence, and risk flags
- `mystics-assets-index-{event_id}.json` — generated paths, selected story angle, timestamp, event ID, writer voice, and risk summary

Editors should treat these as review-ready components, not published copy. The
assets inherit Maya Brooks' voice and reuse the selected story angle, but they
remain deterministic templates grounded only in the normalized ESPN packet and
Mystics editorial memory. Review final score, player stats, headline risk flags,
and any wording that could imply reporting access before using an asset
elsewhere. The asset flow does not publish and does not call Discord, Contentful,
or the NSMT admin API.

Use `--qa` to create an advisory editorial quality report for the generated
article and any assets created in the same run:

```text
drafts/mystics/qa/mystics-qa-{event_id}.json
```

QA reports score each item from 0-100 across factual safety, source support,
clarity, NSMT voice fit, repetition risk, unsupported-claim risk, and publish
readiness. The report also includes issue flags such as missing score, missing
opponent, fake quote risk, too clickbaity, memory overreach, weak headline, and
weak social caption. The overall recommendation is one of:
`approve_for_editor_review`, `needs_human_revision`, or
`reject_and_regenerate`.

Editors should use QA as a triage aid before reading the draft and packet:
start with the lowest-scoring items, then check top issue flags against the
normalized ESPN facts and editorial rules. QA is advisory only. It does not
replace human review, does not approve publishing, and does not post or create
drafts in any external system.

Use `--claim-audit` to create an advisory v0.2 claim evidence audit:

```text
drafts/mystics/claim_audit/mystics-claim-audit-{event_id}.json
```

The audit keeps the backward-compatible top-level `claims` list and adds
sentence-level grounding via `sentence_map` and `sentence_summary`. Sentence
records map deterministic claims to packet evidence, memory context, editorial
rules, weak support, unsupported markers, or obvious contradictions. This is a
local review aid only, not semantic fact-checking and not a publishing gate.

Use `--external-editor-packet` to prepare a structured package for Claude or
another external editor model:

```text
drafts/mystics/external_review/mystics-external-review-{event_id}.json
```

The packet includes the external editor prompt from
`prompts/editors/claude_external_editor.md`, the main article markdown, generated
assets when `--generate-assets` is used, QA summary when `--qa` is used, story
angles, memory context summary, editorial rules, source event ID, and a compact
normalized game packet summary. This only prepares material for external review.
It does not call the Claude API or any other LLM API, does not publish, and does
not automatically replace generated drafts with external edits. Any returned
external edits are advisory and must be applied manually after human review.

After manually sending the external editor packet to Claude or another editor
model, paste/save the model's JSON response to a local file. It must follow the
schema requested in `prompts/editors/claude_external_editor.md`. Then ingest it:

```bash
python -m ingestion.mystics_postgame_recap \
  --fixture tests/fixtures/espn_mystics_postgame_401856918.json \
  --ingest-external-editor-response path/to/external-editor-response.json \
  --discord-review
```

Ingestion validates the response and writes:

```text
drafts/mystics/external_review/responses/mystics-external-editor-response-{event_id}.json
drafts/mystics/external_review/mystics-external-editor-decision-{event_id}.json
```

The decision summary counts publish blockers, unsupported claims, and recommended
edits. `safe_to_publish_candidate` is true only when the external verdict is
`approve` or `approve_with_minor_edits` and there are no publish blockers.
`needs_revision` is true for `needs_revision` or `reject`. `human_editor_required`
is always true. This step never applies edits, rewrites drafts, publishes, or
calls Claude, Discord, Contentful, or the admin API.

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
