"""Stage B acceptance harness — Maya Brooks LLM recap + verifiable-quote guardrail.

Residential-IP only (transcript fetch is blocked from CI per Stage 2). Requires
ANTHROPIC_API_KEY. Enriches the May 24 Mystics @ Seattle packet with transcripts
ON (manual override), runs the LLM writer, then reports the full recap, quote
verification, attribution flags, em-dash check, and token/cost/caching numbers.

Run:
    set -a && . ./.env && set +a   # if the key lives in .env
    uv run --with youtube-transcript-api==1.2.4 python scripts/llm_recap_acceptance.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

from ingestion.espn_mystics import fetch_espn_payloads, load_fixture_payload
from ingestion.mystics_normalizer import build_postgame_packet
from newsroom.claim_audit import format_claim_evidence_audit, verify_quotes
from newsroom.drafts import render_markdown_document
from newsroom.llm_writer import estimate_cost, write_recap
from newsroom.qa import format_editorial_qa_report

FIXTURE = "tests/fixtures/espn_mystics_postgame_401856918.json"
MANUAL_OVERRIDE = [
    {"video_id": "yvVYc7CfIBo", "kind": "highlights"},
    {"video_id": "lZ1U_8wCp6g", "kind": "presser"},
]


def _load_base_payloads():
    try:
        payloads = fetch_espn_payloads(as_of=date(2026, 5, 27))
        if payloads.get("event") or payloads.get("scoreboards"):
            return payloads, "live ESPN (as_of 2026-05-27)"
    except Exception as exc:  # noqa: BLE001
        print(f"[note] live ESPN fetch failed ({type(exc).__name__}: {exc}); using fixture")
    return load_fixture_payload(FIXTURE), f"fixture ({FIXTURE})"


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Cannot run the live LLM acceptance.")
        print("Add it to .env (gitignored) and re-run, or export it for this shell.")
        return 2

    payloads, base_label = _load_base_payloads()
    packet = build_postgame_packet(payloads, include_transcripts=True, transcript_videos=MANUAL_OVERRIDE)
    game = packet["game"]
    media = packet.get("media_transcripts", [])

    print("=" * 72)
    print("STAGE B ACCEPTANCE — Maya Brooks LLM recap + verifiable-quote guardrail")
    print("=" * 72)
    print(f"base packet : {base_label}")
    print(f"game        : {game.get('name')} ({game.get('date','')[:10]}) event {game.get('id')}")
    print(f"transcripts : {[(m['kind'], m.get('status'), m.get('snippet_count')) for m in media]}")
    print()

    recap = write_recap(packet, writer_profile=packet["writer_profile"])
    body = recap["body"]
    qv = recap["quote_verification"]

    print("--- HEADLINE ---")
    print(recap["headline"])
    print("\n--- BODY ---")
    print(body)
    print("\n--- EXCERPT ---")
    print(recap["excerpt"])
    print()

    # Guardrail: every quote must pass the string check; attributed quotes flagged.
    print("--- QUOTE VERIFICATION ---")
    print(f"checked={qv['checked']} verified={qv['verified_count']} unverified={qv['unverified_count']} "
          f"hard_fail={qv['hard_fail']} requires_external_review={qv['requires_external_review']}")
    for q in qv["quotes"]:
        print(f"  [{'OK ' if q['verified'] else 'XX '}ratio={q['match_ratio']:.3f} "
              f"kind={q['matched_kind']} speaker={q['speaker']}] {q['text']!r}")
    uses_presser = any(q["verified"] and q["matched_kind"] == "presser" for q in qv["quotes"]) or any(
        seg.get("kind") == "presser" for seg in qv.get("used_segments", [])
    )
    print(f"uses presser material: {uses_presser}")
    print()

    # House rule: no em dashes.
    em_dashes = body.count("—")
    print("--- HOUSE RULES ---")
    print(f"em dashes in body: {em_dashes}  ({'PASS' if em_dashes == 0 else 'FAIL'})")
    print(f"curly quotes in body: {sum(body.count(c) for c in '“”')}")
    print()

    # Run the same downstream audit/QA the pipeline applies to drafts.
    document = render_markdown_document(packet, headline=recap["headline"], article=body, excerpt=recap["excerpt"])
    audit = format_claim_evidence_audit(packet, article_markdown=document)
    qa = format_editorial_qa_report(packet, article_markdown=document)
    print("--- DOWNSTREAM ---")
    print(f"claim_audit.quote_verification.hard_fail: {audit['quote_verification']['hard_fail']}")
    print(f"qa.main_article.issue_flags: {qa['item_reports']['main_article']['issue_flags']}")
    print(f"qa.overall_recommendation: {qa['overall_recommendation']}")
    print(f"used_segments: {len(qv['used_segments'])} segment(s) traced")
    print()

    # Cost + caching.
    usage = recap["usage"]
    cost = estimate_cost(usage, recap["model"])
    print("--- TOKENS / COST / CACHING ---")
    print(json.dumps({"model": recap["model"], "raw_usage": usage, "estimate": cost}, indent=2))
    print()

    ok = (not qv["hard_fail"]) and em_dashes == 0 and uses_presser
    print(f"ACCEPTANCE: {'PASS' if ok else 'REVIEW'}  "
          f"(hard_fail={qv['hard_fail']}, em_dashes={em_dashes}, uses_presser={uses_presser})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
