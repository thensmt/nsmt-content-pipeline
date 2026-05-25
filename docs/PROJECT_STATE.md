# Project State: Mystics AI Beat Writer MVP

Last updated: 2026-05-25

This document summarizes the current Washington Mystics postgame recap MVP so a future Codex session can orient quickly without rereading the full repository.

## Architecture Overview

The Mystics MVP is an additive local pipeline with a stable CLI entrypoint at `ingestion/mystics_postgame_recap.py`. Focused ingestion and newsroom modules now own the implementation. The pipeline does four things:

1. Fetch or load ESPN game payloads for the Washington Mystics.
2. Normalize schedule, scoreboard, summary, box score, team stats, leaders, scoring by quarter, play-by-play, and gamecast metadata into a JSON packet.
3. Attach Maya Brooks writer context plus persistent Mystics editorial memory.
4. Generate a markdown recap draft and, optionally, secondary editorial assets, editorial QA, a claim evidence audit, an external editor review packet, and/or a Discord-ready review JSON package.

No publishing integrations are invoked. The pipeline does not call Discord, Contentful, Claude, or the NSMT admin API.

## Current Pipeline Flow

Default live path:

1. `fetch_espn_payloads()` pulls ESPN Mystics schedule for the season.
2. The schedule produces candidate scoreboard dates on or before `--as-of`.
3. Daily ESPN scoreboards are checked until the latest completed Mystics game is found.
4. The ESPN summary endpoint is fetched for that event.
5. `build_postgame_packet()` normalizes ESPN data, loads memory, extracts narrative signals, and ranks story angles.
6. `write_outputs()` writes:
   - normalized packet: `data/packets/mystics_postgame_{event_id}.json`
   - markdown draft: `drafts/mystics/mystics-postgame-{YYYY-MM-DD}-{event_id}.md`
7. If `--generate-assets` is used, `write_editorial_assets()` writes:
   - short recap: `drafts/mystics/assets/mystics-short-recap-{event_id}.md`
   - 3 takeaways: `drafts/mystics/assets/mystics-takeaways-{event_id}.md`
   - push alert: `drafts/mystics/assets/mystics-push-alert-{event_id}.txt`
   - newsletter blurb: `drafts/mystics/assets/mystics-newsletter-blurb-{event_id}.md`
   - SEO summary: `drafts/mystics/assets/mystics-seo-summary-{event_id}.md`
   - social caption: `drafts/mystics/assets/mystics-social-{event_id}.txt`
   - headline candidates: `drafts/mystics/assets/mystics-headlines-{event_id}.json`
   - asset index: `drafts/mystics/assets/mystics-assets-index-{event_id}.json`
8. If `--qa` is used, `write_editorial_qa_report()` writes:
   - QA report: `drafts/mystics/qa/mystics-qa-{event_id}.json`
9. If `--claim-audit` is used, `write_claim_evidence_audit()` writes:
   - claim evidence audit: `drafts/mystics/claim_audit/mystics-claim-audit-{event_id}.json`
10. If `--external-editor-packet` is used, `write_external_editor_review_packet()` writes:
   - external editor packet: `drafts/mystics/external_review/mystics-external-review-{event_id}.json`
11. If `--ingest-external-editor-response PATH` is used, `ingest_external_editor_response()` writes:
   - normalized response: `drafts/mystics/external_review/responses/mystics-external-editor-response-{event_id}.json`
   - decision summary: `drafts/mystics/external_review/mystics-external-editor-decision-{event_id}.json`
12. If `--discord-review` is used, `write_discord_review_package()` writes:
   - review package: `drafts/mystics/review/mystics-postgame-{YYYY-MM-DD}-{event_id}-review.json`

Offline fixture path:

```bash
python -m ingestion.mystics_postgame_recap --fixture tests/fixtures/espn_mystics_postgame_401856918.json
```

This exercises the same normalization, memory, angle, draft, and review-package logic without hitting ESPN.

## Important Folders And Files

- `ingestion/mystics_postgame_recap.py`
  Stable CLI orchestrator and backwards-compatible helper import surface.
- `ingestion/espn_mystics.py`
  ESPN schedule, scoreboard, summary fetch flow, and raw fixture loading.
- `ingestion/mystics_normalizer.py`
  Normalized postgame packet creation from ESPN payloads.
- `newsroom/common.py`
  Shared Mystics constants, default local paths, writer fallback profile, and small helper functions.
- `newsroom/schemas.py`
  Plain-Python validation boundaries for normalized packets, story angles, asset indexes, QA reports, external review artifacts, and Discord review packages.
- `newsroom/memory.py`
  Mystics memory loading plus compact memory summaries for review packets.
- `newsroom/story_angles.py`
  Narrative signal extraction, story angle ranking, and angle risk flags.
- `newsroom/drafts.py`
  Main Maya Brooks markdown draft rendering and packet/draft file writing.
- `newsroom/assets.py`
  Secondary editorial asset generation and asset index writing.
- `newsroom/qa.py`
  Advisory local QA scoring and report writing.
- `newsroom/claim_audit.py`
  Deterministic claim evidence audit generation and persisted audit loading.
- `newsroom/external_review.py`
  External editor packet creation and external editor response ingestion.
- `newsroom/discord_review.py`
  Discord-ready local review package formatting and writing.
- `data/writers/maya-brooks.json`
  Maya Brooks writer profile.
- `data/memory/mystics/`
  Persistent editorial memory for the Mystics beat.
- `tests/fixtures/espn_mystics_postgame_401856918.json`
  Saved ESPN payload fixture for offline tests.
- `tests/fixtures/claude_external_editor_response_401856918.json`
  Saved sample external editor JSON response for ingestion tests.
- `tests/test_mystics_postgame_recap.py`
  Unit tests for normalization, memory, story angles, draft generation, and Discord review JSON.
- `drafts/mystics/`
  Generated markdown recap drafts.
- `drafts/mystics/assets/`
  Generated secondary editorial assets and their JSON index.
- `drafts/mystics/qa/`
  Advisory editorial QA reports for generated drafts and assets.
- `drafts/mystics/claim_audit/`
  Advisory claim evidence audits for generated drafts and assets.
- `drafts/mystics/external_review/`
  Local review packets prepared for a future external editor model call.
- `drafts/mystics/external_review/responses/`
  Validated external editor responses saved after manual response ingestion.
- `drafts/mystics/review/`
  Generated Discord review packages.
- `prompts/editors/claude_external_editor.md`
  Prompt template for Claude or another external LLM editor. It requires structured JSON only and no publishing/rewrite action.
- `data/packets/`
  Generated normalized packets. Note: `data/packets/*.json` is currently ignored by `.gitignore`.
- `README.md`
  User-facing usage commands and short MVP description.

## Writer Profile System

Maya Brooks is defined in `data/writers/maya-brooks.json` and mirrored as a fallback constant in `newsroom/common.py`.

Current profile fields:

- `id`
- `name`
- `title`
- `publication`
- `beat`
- `league`
- `voice`
- `focus_areas`
- `guardrails`

The draft uses Maya Brooks as the byline and voice context. The profile is editorial guidance only; it is not a source for game facts.

## Memory System

Persistent memory lives in `data/memory/mystics/`.

Files:

- `season_narratives.json`
  Conservative season-level framing prompts such as possession discipline and quarter response.
- `player_profiles.json`
  Player-specific editorial lenses and avoid lists. These are not bio claims.
- `recent_storylines.json`
  Reusable storyline prompts such as bench texture and chase-game framing.
- `editorial_rules.json`
  Hard editorial limits and default risk flags.

`load_mystics_memory()` loads all four files into the normalized packet under `memory`. Missing or invalid files fail gracefully by recording `missing_files` or `load_errors`; they do not crash packet generation. Missing memory also becomes a risk flag in story-angle selection.

Memory must be treated as editorial context, not hard news fact. Current-game facts must come from ESPN payloads or another named source.

## Story Angle System

`select_story_angles(packet)` produces exactly three ranked story angles. Each angle includes:

- `angle_title`
- `angle_summary`
- `confidence` from `0.0` to `1.0`
- `supporting_signals`
- `risk_flags`

Inputs include:

- final score
- scoring margin
- top performers
- scoring by quarter
- team stats
- play-by-play and gamecast availability
- Mystics memory context

Current angle families:

1. Possession gap angle
2. Scoring-run / quarter-response angle
3. Individual performer entry-point angle

The markdown draft uses the top-ranked angle for headline/body emphasis. The older `narrative["likely_article_angles"]` field remains for compatibility but the structured `story_angles` list is now the primary angle system.

## Schema Validation Boundaries

`newsroom/schemas.py` validates the local artifact contracts without adding dependencies. Validators return the original object when valid and raise `ValueError` with path-specific messages when required fields, core types, ranges, or obvious shapes are wrong. Unknown extra keys are allowed so the pipeline can evolve without breaking every fixture.

Validated artifacts:

- normalized game packets
- story angles
- Discord review packages
- asset indexes
- QA reports
- claim evidence audits
- external editor review packets
- raw external editor responses
- normalized external editor response envelopes
- external editor decision summaries

Validation is applied at safe generation, read, and write boundaries: after packet assembly, before packet/draft writes, when story angles are selected, when asset indexes, QA reports, and claim evidence audits are formatted, when external editor packets/responses/decision summaries are created or read, and when Discord review packages are formatted or assembled from existing local QA/claim-audit/external-review files.

## Multi-Asset Generation Flow

`--generate-assets` creates multiple review-ready assets from the same normalized packet and the selected top-ranked story angle. The flow is deterministic and local; it does not call a model, Discord, Contentful, or the NSMT admin API.

Command:

```bash
python -m ingestion.mystics_postgame_recap \
  --fixture tests/fixtures/espn_mystics_postgame_401856918.json \
  --generate-assets
```

Asset output directory:

```text
drafts/mystics/assets/
```

Generated files:

- `mystics-short-recap-{event_id}.md`
  120-180 words, fast postgame tone.
- `mystics-takeaways-{event_id}.md`
  Exactly three bullets, each with title and explanation.
- `mystics-push-alert-{event_id}.txt`
  Max 160 characters.
- `mystics-newsletter-blurb-{event_id}.md`
  75-120 words, conversational tease.
- `mystics-seo-summary-{event_id}.md`
  One readable, keyword-conscious paragraph.
- `mystics-social-{event_id}.txt`
  Concise Instagram/X-compatible caption with final score and no more than two hashtags.
- `mystics-headlines-{event_id}.json`
  Exactly five ranked headline candidates with `headline`, `tone`, `confidence`, and `risk_flags`.
- `mystics-assets-index-{event_id}.json`
  Includes generated asset paths, selected story angle, generation timestamp, event ID, writer voice, and risk summary.

Editors should use these assets as a packaging kit after reviewing the main draft and normalized packet. The assets inherit Maya Brooks' voice, selected angle, and risk flags, but they are still draft components. Editors should verify final score, player stats, phrasing around scoring runs or quarters, headline risk flags, and any language that could imply reporting access.

Current asset guardrails:

- Uses only packet facts and Mystics memory context.
- Propagates selected-angle risk flags into headline candidates and the asset index.
- Avoids quotes, injury claims, locker-room detail, motivation claims, and milestone language unless explicitly supported.
- Keeps publishing and messaging out of scope.

## Editorial QA Flow

`--qa` creates an advisory JSON quality report for the main article draft and any assets generated in the same run. It is deterministic and local; it does not call a model, Discord, Contentful, or the NSMT admin API.

Commands:

```bash
python -m ingestion.mystics_postgame_recap \
  --fixture tests/fixtures/espn_mystics_postgame_401856918.json \
  --qa

python -m ingestion.mystics_postgame_recap \
  --fixture tests/fixtures/espn_mystics_postgame_401856918.json \
  --generate-assets \
  --qa \
  --discord-review
```

QA output directory:

```text
drafts/mystics/qa/
```

QA report filename:

```text
drafts/mystics/qa/mystics-qa-{event_id}.json
```

The report includes:

- `item_reports` for `main_article`, plus generated assets if present:
  `short_recap`, `takeaways`, `push_alert`, `newsletter_blurb`, `seo_summary`,
  `social_caption`, and `headline_candidates`.
- 0-100 scores for:
  `factual_safety`, `source_support`, `clarity`, `nsmt_voice_fit`,
  `repetition_risk`, `unsupported_claim_risk`, and `publish_readiness`.
- `overall_recommendation`, one of:
  `approve_for_editor_review`, `needs_human_revision`, or `reject_and_regenerate`.
- Issue flags from the supported set:
  `missing_score`, `missing_opponent`, `missing_top_performers`,
  `unsupported_causality`, `fake_quote_risk`, `too_generic`,
  `too_clickbaity`, `too_long`, `too_short`, `headline_weak`,
  `social_caption_weak`, and `memory_overreach`.
- Summary fields for `lowest_scoring_items` and `top_issue_flags`.

Editors should use QA as a triage aid before reading the draft and packet. Start with the lowest-scoring items, inspect the top issue flags, then verify the flagged copy against the normalized packet and editorial rules. QA is advisory only: it does not replace human review, does not authorize publishing, and does not create or post anything externally.

## Claim Evidence Audit Flow

`--claim-audit` creates a deterministic local JSON audit that maps important recap and asset claims to available evidence. It is advisory only; it does not block generation unless the audit JSON shape itself is malformed, and it does not call a model, Discord, Contentful, the NSMT admin API, or any external service.

Command:

```bash
python -m ingestion.mystics_postgame_recap \
  --fixture tests/fixtures/espn_mystics_postgame_401856918.json \
  --generate-assets \
  --claim-audit \
  --discord-review
```

Audit output directory:

```text
drafts/mystics/claim_audit/
```

Audit filename:

```text
drafts/mystics/claim_audit/mystics-claim-audit-{event_id}.json
```

The audit currently emits `schema_version: mystics-claim-evidence-audit/v0.2` and includes:

- `claims`, each with `item_key`, `claim`, `category`, `evidence_paths`, and `notes`
- `claim_categories`: `supported_by_packet`, `supported_by_memory`, `unsupported`, `needs_human_review`, `balance_warning`, and `source_gap`
- `sentence_map`, where each generated sentence gets a stable `sentence_id`, `item_key`, `section`, `text`, `claim_types`, `support_status`, `support_confidence`, `evidence_refs`, `risk_flags`, and `notes`
- `sentence_summary`, including status counts, unsupported/weak/contradiction counts, editorial-rule count, and lowest-confidence sentence IDs
- `support_statuses`: `supported`, `weak`, `unsupported`, `contradiction`, `editorial_rule`, and `not_claim`
- optional `grounding_method_version`
- `source_inventory`, including whether a non-ESPN second source is present
- `summary`, including category counts, warning count, Washington/opponent mention counts, and whether the top Mystics performer is surfaced
- `advisory_only`, `human_editor_required`, and `no_auto_publish`

The audit uses simple deterministic matching against normalized packet fields, memory context, generated text, and deterministic editorial rules. Sentence grounding covers final score/result, venue/date, top Mystics performer, player stat lines, team stat edges, scoring run/key quarter summaries, unsupported markers, memory/trend-language weak support, and obvious contradictions for score, result, venue, date, and player stat values. Editors should treat it as a claim map and triage aid, not as semantic fact-checking.

## External Editor Packet Flow

`--external-editor-packet` creates a structured JSON packet that can be sent manually to Claude or another LLM editor for critique, fact-risk review, and revision suggestions. The command prepares material only; it does not call Claude, Discord, Contentful, the NSMT admin API, or any other external service.

Command:

```bash
python -m ingestion.mystics_postgame_recap \
  --fixture tests/fixtures/espn_mystics_postgame_401856918.json \
  --generate-assets \
  --qa \
  --external-editor-packet
```

External editor output directory:

```text
drafts/mystics/external_review/
```

External editor packet filename:

```text
drafts/mystics/external_review/mystics-external-review-{event_id}.json
```

The packet includes:

- `editor_prompt` loaded from `prompts/editors/claude_external_editor.md`
- `main_article_markdown`
- `generated_assets` when `--generate-assets` is used
- `normalized_game_packet_summary`
- `story_angles`
- `memory_context_summary`
- `internal_qa_summary` when `--qa` is used
- `editorial_rules`
- `source_event_id`
- `generated_timestamp`

The prompt tells the external model to act as a senior sports editor, preserve Maya Brooks' voice, check factual safety, flag unsupported claims, weak headlines, generic AI language, and memory overreach, avoid invented quotes/reporting details, recommend edits only, and return structured JSON only. Expected external response fields are `overall_verdict`, `article_notes`, `asset_notes`, `factual_risks`, `unsupported_claims`, `headline_feedback`, `voice_feedback`, `recommended_edits`, `suggested_headline`, `publish_blockers`, and `confidence`.

External edits are advisory only. The MVP does not automatically replace generated drafts with external edits, does not approve publishing, and does not post or create CMS drafts.

## External Editor Response Ingestion

After manually sending an external editor packet to Claude or another editor model, paste or save the model's structured JSON response to a local file. The response should match the schema requested in `prompts/editors/claude_external_editor.md`.

Sample fixture:

```text
tests/fixtures/claude_external_editor_response_401856918.json
```

Ingest command:

```bash
python -m ingestion.mystics_postgame_recap \
  --fixture tests/fixtures/espn_mystics_postgame_401856918.json \
  --ingest-external-editor-response tests/fixtures/claude_external_editor_response_401856918.json \
  --discord-review
```

Ingestion validates:

- required fields: `overall_verdict`, `article_notes`, `asset_notes`, `factual_risks`, `unsupported_claims`, `headline_feedback`, `voice_feedback`, `recommended_edits`, `suggested_headline`, `publish_blockers`, and `confidence`
- `overall_verdict` is one of `approve`, `approve_with_minor_edits`, `needs_revision`, or `reject`
- `confidence` is a number from 0 to 1
- `publish_blockers`, `recommended_edits`, `unsupported_claims`, and `factual_risks` are lists

Normalized response output:

```text
drafts/mystics/external_review/responses/mystics-external-editor-response-{event_id}.json
```

Decision summary output:

```text
drafts/mystics/external_review/mystics-external-editor-decision-{event_id}.json
```

Decision summary logic:

- `safe_to_publish_candidate` is true only if `overall_verdict` is `approve` or `approve_with_minor_edits` and `publish_blockers` is empty.
- `needs_revision` is true if `overall_verdict` is `needs_revision` or `reject`.
- `human_editor_required` is always true.

Response ingestion is advisory only. It never publishes, never calls Claude, Discord, Contentful, or the NSMT admin API, and never rewrites or replaces generated drafts. A human editor must decide whether and how to apply recommended edits.

## Discord Review Package Flow

`--discord-review` generates a JSON package suitable for later manual or bot posting to a Discord forum/thread.

Command:

```bash
python -m ingestion.mystics_postgame_recap \
  --fixture tests/fixtures/espn_mystics_postgame_401856918.json \
  --discord-review
```

Review package output:

```text
drafts/mystics/review/mystics-postgame-{YYYY-MM-DD}-{event_id}-review.json
```

Review JSON fields:

- `thread_title`
- `summary_message`
- `editor_checklist`
- `article_markdown_path`
- `packet_path`
- `risk_flags`
- `selected_angle`
- `alternate_angles`
- `recommended_status`
- If a QA report is generated and passed into the review package:
  - `qa_report_path`
  - `overall_recommendation`
  - `lowest_scoring_items`
  - `top_issue_flags`
- If a claim evidence audit exists:
  - `claim_audit_path`
  - `claim_audit_summary`
  - sentence-grounding summary fields when available: unsupported sentence count, weak sentence count, contradiction count, and lowest-confidence sentence IDs
- If an external editor packet exists:
  - `external_editor_packet_path`
  - `recommended_external_review`
- If an external editor decision summary exists:
  - `external_editor_decision_path`
  - `external_editor_verdict`
  - `external_editor_confidence`
  - `external_editor_publish_blockers_count`
  - `external_editor_needs_revision`
  - `human_editor_required`

Thread title format:

```text
[Mystics Recap] Opponent vs Washington - YYYY-MM-DD - ESPN Event ID
```

The summary message includes final score, top-ranked angle, top performers, biggest risk flags, draft path, packet path, optional QA/audit/external-review paths, and the required note:

```text
Human review required before publishing.
```

This is a handoff artifact only. It does not post to Discord.

## Current CLI Options

```bash
python -m ingestion.mystics_postgame_recap [options]
```

Options:

- `--as-of YYYY-MM-DD`
  Latest date to consider when searching for the most recent completed game.
- `--season YEAR`
  WNBA season year. Defaults to the `--as-of` year.
- `--fixture PATH`
  Load a saved ESPN payload fixture instead of fetching live ESPN data.
- `--packet-dir PATH`
  Override normalized packet output directory.
- `--draft-dir PATH`
  Override markdown draft output directory.
- `--discord-review`
  Write Discord-ready review JSON. Does not call Discord.
- `--generate-assets`
  Write secondary editorial assets under `drafts/mystics/assets/`. Does not publish or call external APIs.
- `--qa`
  Write advisory editorial QA JSON under `drafts/mystics/qa/`. Scores the main draft and any assets generated in the same run. Does not publish or call external APIs.
- `--claim-audit`
  Write advisory claim evidence audit JSON under `drafts/mystics/claim_audit/`. Maps key claims and sentence-level grounding to packet evidence, memory context, deterministic editorial rules, or warning categories. Does not publish or call external APIs.
- `--external-editor-packet`
  Write a local packet under `drafts/mystics/external_review/` for future Claude or external LLM editor review. Does not call an LLM API, publish, or rewrite source drafts.
- `--ingest-external-editor-response PATH`
  Validate and store a manually saved external editor JSON response, then write a local decision summary. Does not call an LLM API, publish, or apply edits.
- `--dry-run`
  Print normalized JSON and markdown preview without writing files. With `--discord-review`, also prints review JSON preview. With `--generate-assets`, also prints asset and asset-index previews. With `--qa`, also prints QA JSON preview. With `--claim-audit`, also prints claim evidence audit preview. With `--external-editor-packet`, also prints external editor packet preview. With `--ingest-external-editor-response`, also prints normalized response and decision-summary previews.

## Testing Approach

Run all tests:

```bash
python3 -m unittest discover -s tests -v
```

Current Mystics-specific tests cover:

- memory files load correctly
- missing memory files fail gracefully
- ESPN fixture normalizes to the expected game
- narrative signals are extracted
- story angle selector returns exactly three ranked angles
- each angle has required fields
- weak/incomplete play-by-play creates risk flags
- markdown draft stays 600-800 words and includes Editorial Notes
- markdown and packet outputs write to the expected directories
- Discord review package formatter includes required fields
- CLI `--discord-review` creates review JSON
- multi-asset generation writes every asset file and asset index
- headline generator returns exactly five candidates
- push alert stays at or under 160 characters
- takeaways return exactly three bullets
- social caption includes the final score
- SEO summary exists as a single paragraph
- selected-angle risk flags propagate to headline candidates and the asset index
- QA report generation writes `drafts/mystics/qa/mystics-qa-{event_id}.json`
- QA item reports include all required score categories with integer scores from 0 to 100
- QA recommendations stay within the approved recommendation set
- obvious quality problems produce issue flags
- claim evidence audit generation writes `drafts/mystics/claim_audit/mystics-claim-audit-{event_id}.json`
- claim evidence audits flag unsupported interpretation, ESPN-only source gaps, opponent-heavy copy, and missing top-Mystics-performer surfacing
- claim evidence audits include sentence-level grounding for final score, top Mystics performer, team stat edges, unsupported markers, contradictions, and weak memory/trend language
- claim evidence audit schema rejects malformed category/count fields and sentence-summary inconsistencies
- Discord review JSON includes QA path, recommendation, lowest-scoring items, and top issue flags when QA exists
- Discord review JSON includes a valid claim evidence audit path and summary when an audit exists
- Discord review JSON includes sentence-grounding counts from valid v0.2 claim audits
- malformed persisted claim evidence audits fail instead of being silently included in Discord review JSON
- existing CLI commands still work without `--qa`
- external editor prompt includes structured-JSON-only and no-auto-publish instructions
- external editor packet writes `drafts/mystics/external_review/mystics-external-review-{event_id}.json`
- external editor packet includes the prompt, article markdown, story angles, editorial rules, and optional assets/QA summaries
- Discord review JSON includes external editor packet path and `recommended_external_review` when the packet exists
- valid external editor responses ingest successfully
- invalid external editor verdicts, confidence values, and missing fields fail validation
- external editor decision summaries include counts, revision flags, safe-to-publish-candidate logic, and mandatory human-editor flag
- external editor response ingestion does not modify generated draft files
- Discord review JSON includes external editor decision fields when a decision summary exists

The fixture test keeps core behavior testable without live ESPN calls.

## Known Limitations

- ESPN endpoint shapes can change; the parser is defensive and normalized outputs are schema-validated, but the raw ESPN payload shape is still not schema-validated.
- Generated packets under `data/packets/*.json` are ignored by git.
- The markdown writer is deterministic template logic, not a model call.
- The claim evidence audit and sentence grounding use deterministic text/field matching and are not semantic AI fact-checking; weak support can be conservative and some nuanced unsupported claims can still require human detection.
- The recap can sound repetitive because it prioritizes source-grounding over style variation.
- Secondary assets are deterministic templates and can also sound repetitive.
- Story angle confidence is heuristic, not statistical.
- Asset constraints are template-validated, not editor-approved.
- QA scoring is heuristic and advisory; it can miss subtle unsupported claims or flag safe warning language.
- External editor packets are local handoff artifacts only; no Claude/API call is made yet.
- External editor response ingestion trusts only the response JSON shape; it does not verify suggested edits or apply them.
- Play-by-play run detection uses consecutive scoring plays by team; it does not fully model possessions, free throws across substitutions, or lineup context.
- Bench points are inferred from `starter` flags in ESPN box-score rows.
- Memory is manually maintained and can become stale if not reviewed.
- The Discord review package is not posted anywhere yet.
- Asset generation creates local files only and does not create social, push, newsletter, Discord, or CMS posts.
- QA generation creates local JSON only and does not approve or publish anything.
- External editor review packets do not replace drafts with external edits automatically.
- External editor response ingestion creates local normalized response and decision JSON only.
- No Contentful/admin draft creation is wired into this MVP.

## Future Roadmap Ideas

- Add stricter optional schema coverage for raw ESPN payloads if endpoint drift becomes a recurring issue.
- Add a `--memory-dir` CLI option for testing alternate memory sets.
- Add a richer scoring-run detector that understands game clock, possession changes, and quarter boundaries.
- Add WNBA.com or official Mystics source cross-checks for standings, injuries, and official news.
- Add a fact-check/rewrite pass before any CMS handoff.
- Add a Discord bot/manual-post integration that consumes review JSON only after explicit human approval.
- Add Contentful/admin draft creation as a separate gated command, never as a side effect of recap generation.
- Add snapshot tests for markdown and review JSON after the format stabilizes.
- Improve article prose variation while preserving source discipline.

## Assumptions And Guardrails

- ESPN team id for Washington Mystics is `16`.
- ESPN is the current authoritative source for this MVP’s game facts.
- Memory files are editorial context only.
- Current-game facts override memory.
- If data is missing, the pipeline should flag the gap rather than fabricate.
- Generated drafts are for human review, not publication.
- A future publishing layer must be a separate explicit step.

## Important Editorial Rules

- Do not invent quotes.
- Do not invent injuries or availability details.
- Do not invent locker-room, huddle, halftime, or practice details.
- Do not make claims that require reporting access.
- Do not call a stat a season high, career high, first, worst, or similar unless the packet explicitly supports it.
- Do not infer player motivation, coach intent, or private communication.
- Use only normalized game data for scores, stats, leaders, and play sequence.
- Keep AI disclosure in metadata/byline, not as body copy.

## Important Risk Mitigation Rules

- Carry risk flags from selected story angles into markdown Editorial Notes and Discord review JSON.
- Include source event ID and generated timestamp in Editorial Notes.
- Include packet path and draft path in review JSON.
- Include QA report path and QA summary fields in review JSON when QA exists.
- Include external editor packet path and recommended external review flag in review JSON when an external editor packet exists.
- Include external editor decision summary fields in review JSON when an external editor decision exists.
- Preserve the required Discord-review note: `Human review required before publishing.`
- Keep tests fixture-backed so routine verification does not depend on ESPN availability.
- Treat missing memory files as a warning/risk, not a hard failure.
- Avoid trend language unless multiple games are explicitly present in the packet.

## No-Auto-Publish Policy

The Mystics MVP must not publish automatically.

Current pipeline behavior:

- Does not call Discord.
- Does not call Contentful.
- Does not call the NSMT admin API.
- Does not call Claude or another external editor model.
- Does not toggle any article live.
- Does not automatically replace generated drafts with external edits.
- Writes only local files: packet JSON, markdown draft, optional assets, optional QA JSON, optional external editor packet JSON, optional external editor normalized response/decision JSON, and optional review JSON.

Any future publish or CMS draft creation should be implemented as a separate, explicit, human-gated command or workflow.
