# CODEX Handoff — Adversarial architecture review

Repo root: /Users/david/Downloads/Claude/NSMT/content-pipeline
Stage: VERIFY (adversarial)
Timestamp: 2026-05-23

## Runtime context

- Python pipeline. CI in GitHub Actions runs Sonnet 4.6 writer. Mac runs Codex CLI (xhigh reasoning) for fact-check + rewrite. Mac triggers a publish workflow that posts to admin.thensmt.com + Discord.
- Hybrid exists because Codex CLI auth (`~/.codex/auth.json`) can't move to CI.
- Latest session pushed prompt-level fixes (NO_META_COMMENTARY, AI_TELLS_AVOIDANCE, anti-survey-structure rules) and trimmed article length 700-900 → 500-600 words to fit Discord embed limit.

## Findings

### P1 — v2 FAIL does not block publish
- `scripts/codex_rewrite.py:347-349` records the v2 verdict but `scripts/codex_rewrite.py:399-411` triggers `publish-corrected.yml` regardless of v2 outcome.
- `scripts/publish_from_corrected.py:176-199` then saves the draft + posts Discord unconditionally.
- The pipeline has the *complexity* of a quality gate without the *semantics* of one. A v2 = FAIL article still flows through.

### P1 — CI ↔ Mac ↔ CI is likely overbuilt
- GitHub Actions is doing four jobs at once: queue, artifact store, document transport, publish trigger.
- See `.github/workflows/draft-baseline.yml:80-87` (writer + artifact upload), `scripts/codex_rewrite.py:127-175` (Mac polling), `.github/workflows/publish-corrected.yml:77-82` (publish trigger).
- A Mac-only pipeline (write → fact-check → rewrite → publish all locally with the existing admin POST) would eliminate the round-trip and the artifact-as-transport pattern entirely.

### P1 — workflow inputs are a bad document transport
- Full article body, corrections summary, and review-trail URL are passed as `workflow_dispatch` string inputs in `.github/workflows/publish-corrected.yml:35-53`.
- GH workflow inputs cap at ~65k chars and aren't designed for structured documents. This will hit edge cases (escaping, max length, multi-line handling) under load.

### P1 — no idempotent ledger
- State tracks only processed GH run IDs in a JSON file (`scripts/codex_rewrite.py:47-92`).
- Admin POST in `generate_baselines.py:225-247` is a blind create — no upsert key, no dedupe. Today's 4 duplicate Commanders drafts in admin are the symptom.
- A real ledger (article_id keyed by team+date, with a state machine: drafted → fact_checked → rewritten → published) would prevent this.

### P2 — two-pass verification is not justified yet
- No telemetry measures whether v2 catches material errors v1 misses.
- Today's verdict is FAIL → PASS shape, but that's *one* run. Without a body of evidence the second pass is doubling latency + cost on assumption.
- And since v2 doesn't gate publish (P1 above), even when it catches something it doesn't act.

### P2 — rewriter lacks context
- `scripts/codex_rewrite.py:201-248` shows the rewriter sees the article body + fact-check report only.
- It does NOT see: the writer prompt, the team KB, the daily story packet, or `style_guide.py` rules.
- So when it edits, it can't honor the writer's voice constraints or fact-check against the same source set the writer used. It works with a thinner context than the writer did.

### P2 — prompt rules are becoming policy debt
- `style_guide.py:5-16` explicitly documents that rules came from specific recent failures (the 2026-05-23 Commanders test).
- `generate_baselines.py:79-151` keeps layering hard constraints (guardrails, NO_META, AI_TELLS, anti-survey) instead of asking whether the content architecture itself is producing the symptoms.
- Each new prompt rule is essentially a patch. The list will only grow.

### P2 — Discord is wrongly driving article length
- `scripts/publish_from_corrected.py:89-101` puts the full article in the Discord embed description (4096-char hard cap).
- That cap just forced article length down to 500-600 words (`generate_baselines.py:114` and `:136`).
- Reversed dependency: the *display surface* is shaping the *content product*. Discord should be a notification with a link, not the read surface.

### P2 — Phase B has the missing piece
- `PHASE_B_PLAN.md:83-115` already describes the ledger/state-machine model the current hybrid pipeline lacks.
- It was deferred but it's the right shape for what's being half-built now.

## What prior reviewers missed

The Claude Code review session that produced commit `d42596d` framed the question as "are the prompts catching the right things?" That's the wrong altitude. The architecture has a quality-gate-shaped object that doesn't gate. More prompt rules will not fix that.

## Most critical issue

**The system has the complexity of a quality gate without the semantics of one.** A v2 FAIL still publishes. Stop adding prompt fixes. Choose between:
- (a) A simpler Mac-owned pipeline that drops the CI round-trip entirely, OR
- (b) A real Phase B ledger-based pipeline with state-machine semantics where v2 PASS is a precondition for publish.

Either path is a real choice. The current shape — CI ↔ Mac ↔ CI with a fact-check loop that doesn't gate — is the worst of both.

## Prompt for next tool / session

Ask the user: simpler Mac-owned pipeline (option a) or ledger-based Phase B (option b). Do NOT keep tuning prompts. Once architecture is chosen, the prompt-engineering work has a sane container.
