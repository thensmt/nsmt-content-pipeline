#!/usr/bin/env bash
#
# run_mystics_recap.sh — safe two-step runner for the Mystics LLM postgame recap.
#
# Why two steps: discovery's repeat-matchup disambiguation is still unproven, so
# we confirm WHICH transcript videos get picked before generating anything. No
# fire-and-forget one-liner yet.
#
#   Step 1 (default): pre-flight checks, then discover today's Mystics
#                     highlight/presser videos, print them, and STOP. Prints the
#                     exact Step 2 command with those video IDs as overrides.
#   Step 2 (--go):    fetch transcripts, generate the LLM recap, run the name +
#                     quote gates, the Codex fact-check, and post a Discord REVIEW
#                     drop. Human-gated; NO public-site publish. Deterministic
#                     fallback stays intact on any hard-fail.
#
# origin/main is read-only; this script never publishes to the public site.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

PIN="youtube-transcript-api==1.2.4"

usage() {
  cat <<'EOF'
run_mystics_recap.sh — safe two-step Mystics LLM recap runner

USAGE
  Step 1 (discover + confirm; does NOT generate):
    scripts/run_mystics_recap.sh [--date YYYY-MM-DD] [--opponent "Team Name"]

  Step 2 (generate + Codex fact-check + Discord REVIEW drop):
    scripts/run_mystics_recap.sh --go --transcript-video VIDEO_ID:KIND \
        [--transcript-video VIDEO_ID:KIND ...] [--date YYYY-MM-DD]

OPTIONS
  --date YYYY-MM-DD       Game date / as-of date. Default: today (most recent
                          completed Mystics game is resolved from ESPN).
  --opponent "Team Name"  Skip ESPN opponent resolution in Step 1.
  --transcript-video ID:KIND   Manual transcript override. KIND = highlights | presser.
                          Repeatable. Required for Step 2.
  --go                    Run Step 2 (generation + review drop). Without it, runs Step 1.
  -h, --help              Show this help.

WHAT STEP 2 RUNS
  python -m ingestion.mystics_postgame_recap \
      --include-transcripts --llm-writer --review-drop --qa --claim-audit \
      --transcript-video ... [--as-of DATE]

  - Verbatim-quote gate + roster/coach name gate; either hard-fail falls back to
    the deterministic draft.
  - Codex fact-check (GPT-5 via codex CLI) on the recap.
  - Discord REVIEW drop to the Mystics channel via the existing proxy, with the
    Codex verdict + per-quote transcript timestamp links. human_editor_required
    stays true; nothing is saved to the public site.

EXAMPLES
  scripts/run_mystics_recap.sh
  scripts/run_mystics_recap.sh --go \
      --transcript-video abc123:highlights --transcript-video def456:presser
EOF
}

# ── parse args ────────────────────────────────────────────────────────────────
DATE=""
OPP=""
GO=0
TVIDEOS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --go) GO=1; shift ;;
    --date) DATE="${2:-}"; shift 2 ;;
    --opponent) OPP="${2:-}"; shift 2 ;;
    --transcript-video) TVIDEOS+=("${2:-}"); shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; echo >&2; usage; exit 2 ;;
  esac
done

# ── load .env (repo root) ───────────────────────────────────────────────────────
if [[ -f .env ]]; then
  set -a; source .env; set +a
fi

# ── pre-flight: fail fast with a clear message BEFORE any generation ────────────
preflight() {
  local missing=()
  local k
  for k in ANTHROPIC_API_KEY DISCORD_PROXY_URL DISCORD_PROXY_SECRET; do
    [[ -n "${!k:-}" ]] || missing+=("$k")
  done
  if (( ${#missing[@]} > 0 )); then
    echo "PRE-FLIGHT FAIL: missing env var(s): ${missing[*]}" >&2
    echo "  Add them to $REPO/.env (one KEY=VALUE per line) and re-run." >&2
    exit 1
  fi

  if ! command -v codex >/dev/null 2>&1; then
    echo "PRE-FLIGHT FAIL: codex CLI not found on PATH." >&2
    echo "  The Codex fact-check cannot run. Install codex, then: codex login" >&2
    exit 1
  fi
  if [[ ! -f "$HOME/.codex/auth.json" ]]; then
    echo "PRE-FLIGHT FAIL: codex is not logged in (no ~/.codex/auth.json)." >&2
    echo "  Run:  codex login        (ChatGPT auth), then re-run this script." >&2
    echo "  (Without it the fact-check silently degrades to UNKNOWN.)" >&2
    exit 1
  fi

  echo "pre-flight OK: ANTHROPIC_API_KEY / DISCORD_PROXY_URL / DISCORD_PROXY_SECRET set;" \
       "codex reachable ($(codex --version 2>/dev/null | head -1 || echo 'unknown'))."
}

preflight

# ── Step 2: generate + review drop ──────────────────────────────────────────────
if (( GO == 1 )); then
  if (( ${#TVIDEOS[@]} == 0 )); then
    echo "Step 2 (--go) needs at least one --transcript-video VIDEO_ID:KIND." >&2
    echo "Run Step 1 first (no --go) to discover and confirm the videos." >&2
    exit 2
  fi
  TV_ARGS=()
  for tv in "${TVIDEOS[@]}"; do
    if [[ "$tv" != *:* ]]; then
      echo "Bad --transcript-video '$tv' (expected VIDEO_ID:KIND, KIND=highlights|presser)." >&2
      exit 2
    fi
    TV_ARGS+=(--transcript-video "$tv")
  done
  DATE_ARGS=()
  [[ -n "$DATE" ]] && DATE_ARGS+=(--as-of "$DATE")

  echo "STEP 2: generating LLM recap + Codex fact-check + Discord REVIEW drop (no public publish)..."
  echo "  overrides: ${TVIDEOS[*]}"
  exec uv run --with "$PIN" python -m ingestion.mystics_postgame_recap \
    --include-transcripts --llm-writer --review-drop --qa --claim-audit \
    "${TV_ARGS[@]}" "${DATE_ARGS[@]}"
fi

# ── Step 1: discover + confirm (no generation) ──────────────────────────────────
echo "STEP 1: discovering transcript videos (no generation). Confirm the picks, then run Step 2."
NSMT_DISC_DATE="$DATE" NSMT_DISC_OPP="$OPP" uv run python - <<'PY'
import os
import sys
from datetime import date as _date

from ingestion.fetchers.youtube_transcripts import discover_game_videos

MYSTICS = "Washington Mystics"
date_str = (os.environ.get("NSMT_DISC_DATE") or "").strip()
opp = (os.environ.get("NSMT_DISC_OPP") or "").strip()

try:
    as_of = _date.fromisoformat(date_str) if date_str else _date.today()
except ValueError:
    print(f"Bad --date {date_str!r}; expected YYYY-MM-DD.", file=sys.stderr)
    sys.exit(2)

game_date = date_str or as_of.isoformat()

# Resolve opponent + actual game date from ESPN (most recent completed Mystics
# game on/before --date) unless an explicit --opponent was given.
if not opp:
    try:
        from ingestion.espn_mystics import fetch_espn_payloads
        from ingestion.mystics_normalizer import build_postgame_packet

        packet = build_postgame_packet(fetch_espn_payloads(as_of=as_of))
        teams = [t.get("name") for t in packet["game"].get("teams", [])]
        opp = next((t for t in teams if t and "Mystics" not in t), "")
        game_date = (packet["game"].get("date") or game_date)[:10]
        print(f"resolved game: {packet['game'].get('name')} ({game_date}) event {packet['game'].get('id')}")
    except Exception as exc:  # noqa: BLE001
        print(f"could not resolve opponent from ESPN ({type(exc).__name__}: {exc}).", file=sys.stderr)
        print("Re-run with --opponent \"Team Name\".", file=sys.stderr)
        sys.exit(3)

print(f"discovering for: {MYSTICS} vs {opp}  (game_date={game_date})\n")
picks = discover_game_videos(game_date, [MYSTICS, opp])

if not picks:
    print("No candidate highlight/presser videos found yet.")
    print("If the game just ended they may not be posted; re-run later, or pass the")
    print("video IDs directly to Step 2 with --transcript-video VIDEO_ID:KIND.")
    sys.exit(0)

print(f"{len(picks)} candidate pick(s):")
overrides = []
for p in picks:
    print(f"  [{p['kind']:10}] {p['video_id']}  upload={p.get('upload_date')}  channel={p['channel']}")
    print(f"      {p['title']}")
    overrides.append(f"--transcript-video {p['video_id']}:{p['kind']}")

date_suffix = f" --date {date_str}" if date_str else ""
print("\nIf those are correct, run STEP 2:\n")
print(f"  ./scripts/run_mystics_recap.sh --go " + " ".join(overrides) + date_suffix)
PY
