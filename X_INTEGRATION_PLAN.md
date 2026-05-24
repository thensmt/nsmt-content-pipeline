# X Integration Plan — NSMT Content Pipeline

Owner: David Gaylor
Date: 2026-05-23
Status: PROPOSAL — not yet built

## Goal

Auto-generate an X (Twitter) preview tweet alongside every article. Tweet drops at the same moment the website article goes live. "Drop in drafts first" — humans review tweet copy before approving publish.

## Architecture summary

**Option B (CI-owned) + SQLite ledger + scheduled drop.**

Why:
- Daily sports content needs reliable cron. Laptop sleeping can't break publish.
- Keeps secrets in GH (consistent with current "no publish secrets on Mac" rule).
- Same-time atomic-ish publish (~1s gap between admin live and tweet) is sufficient for human perception.
- Scheduled drop unlocks embargo workflows ("approve at 4pm, drop at 6am tomorrow").

## The new flow

```
EXISTING PIPELINE (unchanged through v2):
  CI: Sonnet writes draft → upload artifact
  Mac: poll → Codex fact-check v1 → if !PASS, rewrite → Codex fact-check v2
  Mac: bundle review_trail.md
  Mac: trigger publish-corrected.yml (saves as is_active=False draft)

NEW STEPS:
  Mac: write ledger row (status=rewritten, admin_blog_id=BLOG#xxx)
  Mac: generate tweet text via Sonnet, save to ledger row
  Mac: post tweet draft preview to Discord #tweet-drafts

  HUMAN: reviews article (admin) + tweet text (Discord)
  HUMAN: approves with optional schedule → flips ledger to status=approved
         (manual via `gh workflow run approve-publish.yml` OR Discord command)

  CI cron (every 5 min): publish-scheduled.yml polls ledger for
       status=approved AND scheduled_at <= now()
    For each:
      1. PATCH admin /admin/blogs/{id} → is_active=True
      2. Wait ~3s for admin URL to be reachable (poll until 200 OK)
      3. POST X tweet with article URL
      4. Update ledger: status=live, admin_live_at + tweet_live_at + tweet_id
    On admin failure: bail, leave status=approved, log last_error
    On X failure: keep admin live, status=admin_live, queue retry
```

## Ledger — SQLite, single table

`data/ledger.db` (gitignored — treated as authoritative state). One row per article.

```sql
CREATE TABLE articles (
  article_id      TEXT PRIMARY KEY,    -- e.g. commanders-2026-05-23-baseline
  team            TEXT NOT NULL,
  article_date    DATE NOT NULL,
  article_type    TEXT NOT NULL,       -- baseline | recap | preview
  title           TEXT NOT NULL,

  -- Lifecycle status (linear progression):
  --   drafted → fact_checked → rewritten → approved → admin_live → live
  --   Terminal: failed | cancelled
  status          TEXT NOT NULL DEFAULT 'drafted',

  -- Generation artifacts
  body_path       TEXT,                -- path to corrected.md on Mac
  v1_verdict      TEXT,
  v2_verdict      TEXT,

  -- Tweet
  tweet_text      TEXT,
  tweet_id        TEXT,                -- returned by X API after POST

  -- Publishing
  admin_blog_id   TEXT,                -- BLOG#xxx
  admin_url       TEXT,                -- https://thensmt.com/...
  scheduled_at    DATETIME,            -- NULL = approve = drop now; set = drop later
  admin_live_at   DATETIME,
  tweet_live_at   DATETIME,

  -- Error tracking + audit
  last_error      TEXT,
  last_attempt_at DATETIME,
  created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_status ON articles(status);
CREATE INDEX idx_scheduled ON articles(scheduled_at) WHERE scheduled_at IS NOT NULL;
```

**Idempotency:** every publish step checks `_live_at` columns before acting. If `admin_live_at` is set, skip admin POST. If `tweet_live_at` is set, skip tweet POST. Safe to re-run.

**State location:** `data/ledger.db` lives on the Mac, NOT in CI. CI gets ledger context via the workflow_dispatch inputs (small fields only: article_id, scheduled_at, tweet_text). This keeps ledger management local while CI executes the publish.

## Tweet prompt (Sonnet 4.6)

Reuse style_guide.py NO_META_COMMENTARY. Add tweet-specific constraints:

```
You are writing a 280-character X (Twitter) post promoting a sports article.

HARD RULES:
- 280 char MAX total INCLUDING the article URL (which counts as 23 chars on X)
- So your text budget is 257 chars + the URL appended at end
- Lead with the hook: what happened, the score, the player, the decision
- NO emojis
- NO hashtags unless one genuinely natural team tag (#Commanders, #HTTC)
- NO "Check out" / "Read more" / "Here's our take on" — let the hook do the work
- NEVER mention NSMT, "our latest," "this piece," any meta-framing
- Plain text only
- Contractions encouraged
- One sentence, OR two short sentences

Article excerpt:
{first_200_words_of_article}

Article URL: {url}

Output ONLY the tweet text, nothing else. URL will be appended automatically.
```

## X API integration

**Auth:** OAuth 1.0a User Context (simpler for app posting as a fixed account).
- Required GH Secrets:
  - `X_API_KEY` (app consumer key)
  - `X_API_SECRET` (app consumer secret)
  - `X_ACCESS_TOKEN` (user access token for @NSMTsports)
  - `X_ACCESS_TOKEN_SECRET`

**Tier:** Start with Free ($0). 500 writes/month is well above expected 30-90/month for one team. Bump to Basic ($200/mo) only when scaling past 4-5 teams.

**API surface used:** Just `POST /2/tweets` and `DELETE /2/tweets/:id` (the latter only for failed-publish rollback). No timelines, no DMs, no user lookup.

**Code:** ~80 lines in `scripts/x_client.py`. Use `requests_oauthlib` for OAuth1.

## File changes

### New files
- `scripts/ledger.py` — SQLite CRUD wrapper (~120 lines)
- `scripts/generate_tweet.py` — Sonnet tweet generation (~80 lines)
- `scripts/x_client.py` — X API wrapper (~80 lines)
- `scripts/publish_live.py` — atomic admin+X publish (~150 lines)
- `.github/workflows/publish-scheduled.yml` — cron polls ledger, runs publish-live
- `.github/workflows/approve-publish.yml` — manual approval entrypoint
- `data/.gitkeep` (the ledger.db is gitignored)

### Modified files
- `scripts/codex_rewrite.py` — after v2 step, write ledger row + call generate_tweet + post preview to Discord
- `scripts/publish_from_corrected.py` — repurposed: now SAVES as inactive draft only (no Discord notification — that moves to publish_live)
- `.gitignore` — add `data/ledger.db`

### Deleted files
- None yet — old `publish_from_corrected.py` stays, just narrower scope

## Implementation order

| Phase | What | Time | Reversible? |
|---|---|---|---|
| 1 | SQLite ledger + CRUD helpers + backfill 4 existing drafts | 2 hr | Yes |
| 2 | Tweet draft generation (Sonnet) + Discord preview, no X yet | 2 hr | Yes |
| 3 | `publish_live.py` for admin-only (flips is_active=True), no X | 2 hr | Yes |
| 4 | X API integration (`x_client.py`) + test post to a private dev tweet | 3 hr | Yes |
| 5 | Wire X into `publish_live.py` atomic flow | 1 hr | Yes |
| 6 | `publish-scheduled.yml` cron + approval mechanism | 3 hr | Yes |
| **Total** | **~13 hr** | | |

Ship Phase 1-3 first (no X creds needed). Validate ledger + tweet drafting + admin-only publish on one Commanders article. THEN add X.

## Failure modes & mitigations

| Failure | Impact | Mitigation |
|---|---|---|
| Admin POST fails | No publish, status stays `approved` | Log + retry queue. Discord alert. |
| Admin URL not yet live (race) | Tweet links to 404 | Poll admin URL until 200 OK before tweet (max 10s) |
| X API rate limit (429) | Tweet not posted, admin already live | Status=admin_live. Cron retry until success. Manual fallback: copy tweet text from ledger. |
| X API auth fails | Tweet not posted | Same as above. Admin URL is live regardless. |
| Tweet > 280 chars | API rejects | Pre-validate client-side. Truncate excerpt or regenerate. |
| Both succeed but ledger update fails | Inconsistent state | Wrap ledger update in transaction. On failure, the next cron run sees `admin_live_at` set but `tweet_live_at` unset and re-attempts tweet (will get duplicate-post error from X, which we treat as success and update ledger). |
| Tweet posts twice | Public embarrassment | Idempotency guard: check `tweet_live_at` before POST. X API returns 187 "duplicate" on identical text within ~5 min, which we treat as success. |
| Sonnet generates tweet with NSMT meta-commentary | Same problem as articles | Prompt reuses NO_META_COMMENTARY. Also validate tweet text contains no "NSMT" before saving to ledger. |

## What this plan deliberately does NOT do (yet)

- **No automatic tweet thread for long articles.** One tweet per article, period.
- **No image generation/attachment.** Text-only tweets. Image automation is a later phase.
- **No reply/quote-tweet handling.** Outbound publish only.
- **No analytics ingestion** (engagement, impressions). One-way push.
- **No tweet editing.** X allows edits within 30 min for premium users; not building that.
- **No multi-account support.** Just @nsmtsports.
- **No real Discord bot.** Phase 5-6 approval can be `gh workflow run` from terminal or a Discord webhook URL the user pastes into a button.

## Open questions for review

1. Should `scheduled_at` default to "drop in 5 minutes" on approval, so there's a brief window to cancel? Or default to "drop now"?
2. If admin save succeeds but X post fails, should we POST to Discord #recap-pipeline with an alert? Or just log it?
3. Should the ledger live in `data/ledger.db` on Mac, or in a tiny Supabase/Turso instance so CI can read/write directly? (Current plan: Mac-local; CI gets context via workflow inputs.)
4. Tweet preview in Discord — do we want a "Edit tweet" affordance, or accept-as-generated only?
5. For the X handle being posted from — is it @nsmtsports? Need to confirm and set up developer access.
6. Free tier vs Basic — start Free until volume forces upgrade?
