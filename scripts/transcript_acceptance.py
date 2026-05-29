"""Stage A acceptance harness — transcript acquisition + packet attachment.

Residential-IP only (Stage 2 proved CI/datacenter IPs are blocked). Enriches a
Mystics packet with transcripts ON via the manual override (bypassing channel
discovery) and prints the media_transcripts block + validation result.

Run:
    uv run --with youtube-transcript-api==1.2.4 python scripts/transcript_acceptance.py
"""

from __future__ import annotations

import json
from datetime import date

from ingestion.espn_mystics import fetch_espn_payloads, load_fixture_payload
from ingestion.mystics_normalizer import build_postgame_packet
from newsroom.schemas import validate_normalized_game_packet

FIXTURE = "tests/fixtures/espn_mystics_postgame_401856918.json"
MANUAL_OVERRIDE = [
    {"video_id": "yvVYc7CfIBo", "kind": "highlights"},
    {"video_id": "lZ1U_8wCp6g", "kind": "presser"},
]


def _trunc(text: str, limit: int = 180) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit].rstrip() + f"… [{len(text)} chars total]"


def _load_base_payloads() -> tuple[dict, str]:
    """Prefer the live May-27 Seattle game; fall back to the committed fixture."""
    try:
        payloads = fetch_espn_payloads(as_of=date(2026, 5, 27))
        if payloads.get("event") or payloads.get("scoreboards"):
            return payloads, "live ESPN (as_of 2026-05-27)"
    except Exception as exc:  # noqa: BLE001 - acceptance harness, report and fall back
        print(f"[note] live ESPN fetch failed ({type(exc).__name__}: {exc}); using fixture")
    return load_fixture_payload(FIXTURE), f"fixture ({FIXTURE})"


def main() -> int:
    payloads, base_label = _load_base_payloads()

    packet = build_postgame_packet(
        payloads,
        include_transcripts=True,
        transcript_videos=MANUAL_OVERRIDE,
    )
    game = packet["game"]
    media = packet.get("media_transcripts", [])

    print("=" * 70)
    print("STAGE A ACCEPTANCE — transcript acquisition + packet attachment")
    print("=" * 70)
    print(f"base packet     : {base_label}")
    print(f"game            : {game.get('name')}  ({game.get('date', '')[:10]})  event {game.get('id')}")
    print(f"schema_version  : {packet.get('schema_version')}")
    print(f"media_transcripts entries: {len(media)}")
    print()

    # --- media_transcripts block (text truncated) ---
    display = []
    for item in media:
        row = {k: item.get(k) for k in ("video_id", "kind", "status", "track", "language", "snippet_count", "char_count")}
        if item.get("status") == "ok":
            row["segments_first2"] = item.get("segments", [])[:2]
            row["text"] = _trunc(item.get("text", ""))
            row["corrected_text"] = _trunc(item.get("corrected_text", ""))
            row["name_corrections"] = item.get("name_corrections", [])
        else:
            row["reason"] = item.get("reason")
        row["source_url"] = item.get("source_url")
        display.append(row)
    print("--- media_transcripts block (truncated) ---")
    print(json.dumps(display, indent=2))
    print()

    # --- name-correction before/after (look for the Amoore fix) ---
    print("--- name-correction before/after ---")
    for item in media:
        if item.get("status") != "ok":
            continue
        corrections = item.get("name_corrections", [])
        print(f"  {item['kind']} ({item['video_id']}): {len(corrections)} correction type(s): "
              f"{[(c['from'], c['to'], c['count']) for c in corrections]}")
        for raw_seg, cor_seg in zip(item.get("segments", []), item.get("corrected_segments", [])):
            if raw_seg.get("text") != cor_seg.get("text") and "Amoore" in cor_seg.get("text", ""):
                print(f"    BEFORE: {raw_seg['text']!r}")
                print(f"    AFTER : {cor_seg['text']!r}")
                break
    print()

    # --- sources provenance ---
    print("--- sources (YouTube entries) ---")
    for src in packet.get("sources", []):
        if "YouTube" in src.get("name", ""):
            print(f"  {src['name']} -> {src['url']} ({src['retrieved_at']})")
    print()

    # --- validation ---
    try:
        validate_normalized_game_packet(packet)
        print("VALIDATION: PASS (schema mystics-postgame-recap/v0.2)")
    except ValueError as exc:
        print(f"VALIDATION: FAIL -> {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
