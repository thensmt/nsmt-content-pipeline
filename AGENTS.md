# AGENTS.md

## Project Purpose
- NSMT content pipeline for local, source-grounded sports draft generation and review.
- Current Mystics MVP creates packets, drafts, assets, QA, and review handoff files only.

## Core Workflow
- Read `docs/PROJECT_STATE.md` first in every new coding session.
- Inspect relevant code and tests before editing.
- Preserve existing CLI behavior unless the task explicitly changes it.
- Update `docs/PROJECT_STATE.md` after major architecture or workflow changes.

## Recommended Workflow For Codex Sessions
- Start with `git status --short`.
- Read `docs/PROJECT_STATE.md`.
- Locate the relevant functions and tests with `rg`.
- Make the smallest coherent change.
- Add or update fixture-backed tests.
- Run `python3 -m unittest discover -s tests -v` for code or behavior changes.

## Editorial Guardrails
- Never fabricate quotes.
- Never fabricate injuries, availability, locker-room, huddle, halftime, or practice details.
- Never infer player motivation, coach intent, or private communication.
- Use normalized packet facts for scores, stats, leaders, and play sequence.
- Treat memory as editorial context, not a source of current-game facts.
- Preserve Maya Brooks voice consistency: clear, restrained, basketball-literate, and source-aware.

## No-Auto-Publish Policy
- Never auto-publish.
- Human editor approval is mandatory.
- Do not call Discord, Contentful, NSMT admin, Claude, or other external publishing/review APIs unless explicitly implementing a gated integration.
- Do not toggle live status or create CMS/social/push posts as a side effect.

## Testing Requirements
- Add tests for all new logic.
- Prefer deterministic, fixture-backed unit tests.
- Keep existing commands working without new flags.
- For docs-only changes, note that tests were not run.

## File Modification Boundaries
- Keep diffs focused and minimal.
- Do not modify production code for docs-only tasks.
- Do not rewrite generated drafts with external editor responses.
- Do not edit generated output files unless the task is to generate or verify artifacts.
- Avoid introducing unnecessary dependencies.

## Memory/Context Rules
- Current-game packet data overrides memory.
- Missing memory should create warnings or risk flags, not fabricated substitutes.
- Avoid trend, milestone, or historical claims unless the packet or explicit source supports them.
- Keep memory-derived language framed as editorial context.

## Asset Generation Rules
- Assets must derive from the same normalized packet and selected top story angle.
- Assets inherit Maya Brooks voice, editorial rules, and risk flags.
- Short assets must stay factual, non-speculative, and free of fake quotes.
- Generated assets are review-ready components, not publish-ready approvals.

## External Editor Workflow
- External editor packets are local handoff files only.
- External editor response ingestion validates, normalizes, and summarizes JSON only.
- External edits are advisory; never apply them automatically.
- `human_editor_required` must remain true for decision summaries.

## Preferred Coding Approach
- Favor readable Python over framework-heavy abstractions.
- Prefer deterministic logic over hidden LLM behavior.
- Use structured parsing/data shapes instead of ad hoc string handling where practical.
- Keep new helpers close to the workflow they support unless reuse is real.

## Repo Safety Rules
- Do not use destructive git commands unless explicitly requested.
- Do not revert user changes.
- Do not add dependencies without a clear requirement.
- Do not call external APIs during tests.

## Deterministic Behavior Preference
- Prefer explicit templates, schemas, and validation.
- Make generated paths, timestamps, flags, and summaries observable in JSON outputs.
- Keep live network behavior out of routine tests.

## Output Expectations
- Final responses should list changed files and tests run.
- Include generated paths or sample outputs when the task asks for them.
- State clearly when tests were not run and why.
- Do not imply anything was published or externally posted.

## Review Expectations
- For code reviews, lead with findings by severity and include file/line references.
- Prioritize bugs, regressions, factual-risk gaps, and missing tests.
- For editorial workflow changes, confirm safeguards remain intact.
