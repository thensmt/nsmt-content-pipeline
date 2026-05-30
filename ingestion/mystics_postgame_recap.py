"""CLI orchestrator for the Washington Mystics postgame recap MVP.

The focused implementation lives in ingestion.espn_mystics,
ingestion.mystics_normalizer, and newsroom.* modules. This module keeps the
stable CLI entrypoint and re-exports the public helpers used by older tests or
callers. It writes local review artifacts only and does not publish.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path

from ingestion.espn_mystics import fetch_espn_payloads, load_fixture_payload
from ingestion.mystics_normalizer import build_postgame_packet
from newsroom.assets import (
    format_asset_index,
    generate_editorial_assets,
    write_editorial_assets,
    _preview_asset_paths,
)
from newsroom.common import (
    DEFAULT_DRAFT_DIR,
    DEFAULT_PACKET_DIR,
    DEFAULT_REVIEW_DIR,
    DEFAULT_ASSET_DIR,
    DEFAULT_QA_DIR,
    DEFAULT_CLAIM_AUDIT_DIR,
    DEFAULT_EXTERNAL_REVIEW_DIR,
    DEFAULT_EXTERNAL_RESPONSE_DIR,
    DEFAULT_WRITER_PROFILE,
    DEFAULT_MEMORY_DIR,
    EXTERNAL_EDITOR_PROMPT_PATH,
    MAYA_BROOKS_PROFILE,
    PROJECT_ROOT,
    TEAM_ABBR,
    TEAM_ID,
    TEAM_NAME,
    _display_path,
)
from newsroom.claim_audit import (
    format_claim_evidence_audit,
    write_claim_evidence_audit,
    load_claim_evidence_audit,
    _preview_claim_audit_path,
)
from newsroom.discord_review import (
    EDITOR_CHECKLIST,
    format_discord_review_package,
    write_discord_review_package,
)
from newsroom.drafts import render_markdown_draft, write_outputs
from newsroom.external_review import (
    EXTERNAL_EDITOR_RESPONSE_FIELDS,
    EXTERNAL_EDITOR_VERDICTS,
    format_external_editor_decision_summary,
    format_external_editor_review_packet,
    ingest_external_editor_response,
    load_external_editor_prompt,
    load_external_editor_response,
    normalize_external_editor_response,
    validate_external_editor_response,
    write_external_editor_review_packet,
)
from newsroom.memory import MEMORY_FILES, load_mystics_memory
from newsroom.qa import (
    QA_ISSUE_FLAGS,
    QA_RECOMMENDATIONS,
    QA_SCORE_CATEGORIES,
    format_editorial_qa_report,
    write_editorial_qa_report,
)
from newsroom.story_angles import extract_narrative_signals, select_story_angles


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a Mystics postgame recap MVP from ESPN data.")
    parser.add_argument("--as-of", type=_parse_date, default=date.today(), help="Latest date to consider, YYYY-MM-DD.")
    parser.add_argument("--season", type=int, default=None, help="WNBA season year. Defaults to --as-of year.")
    parser.add_argument("--fixture", default=None, help="Path to saved ESPN payload fixture for offline generation.")
    parser.add_argument("--packet-dir", type=Path, default=DEFAULT_PACKET_DIR)
    parser.add_argument("--draft-dir", type=Path, default=DEFAULT_DRAFT_DIR)
    parser.add_argument(
        "--discord-review",
        action="store_true",
        help="Write a Discord-ready review JSON package. Does not call Discord.",
    )
    parser.add_argument(
        "--generate-assets",
        action="store_true",
        help="Write secondary editorial assets under the Mystics draft assets directory.",
    )
    parser.add_argument(
        "--qa",
        action="store_true",
        help="Write an advisory editorial QA report for generated local outputs.",
    )
    parser.add_argument(
        "--claim-audit",
        action="store_true",
        help="Write a deterministic local claim evidence audit JSON.",
    )
    parser.add_argument(
        "--external-editor-packet",
        action="store_true",
        help="Write a local packet for external LLM editor review. Does not call any LLM API.",
    )
    parser.add_argument(
        "--ingest-external-editor-response",
        type=Path,
        default=None,
        help="Validate and store an external editor JSON response. Does not apply edits.",
    )
    parser.add_argument(
        "--include-transcripts",
        action="store_true",
        help="Attach the media_transcripts block (Mac-side / residential IP). Also via NSMT_INCLUDE_TRANSCRIPTS.",
    )
    parser.add_argument(
        "--transcript-video",
        action="append",
        default=[],
        metavar="VIDEO_ID:KIND",
        help="Manual transcript override, repeatable (e.g. yvVYc7CfIBo:highlights). Bypasses channel discovery.",
    )
    parser.add_argument(
        "--llm-writer",
        action="store_true",
        help="Generate the recap with the Maya Brooks LLM writer (default off). Also via NSMT_LLM_WRITER. "
             "Falls back to the deterministic draft on API failure or an unsalvageable quote/name hard-fail.",
    )
    parser.add_argument(
        "--review-drop",
        action="store_true",
        help="LLM mode only: run the Codex fact-check and post a Discord REVIEW drop (human-gated, "
             "no public-site publish). Also via NSMT_LLM_REVIEW_DROP. Requires codex CLI + Discord proxy creds.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print normalized JSON and draft path preview without writing.")
    args = parser.parse_args(argv)

    if args.fixture:
        payloads = load_fixture_payload(args.fixture)
    else:
        payloads = fetch_espn_payloads(as_of=args.as_of, season=args.season)

    include_transcripts = bool(args.include_transcripts) or _env_flag("NSMT_INCLUDE_TRANSCRIPTS")
    transcript_videos = _parse_transcript_videos(args.transcript_video)
    packet = build_postgame_packet(
        payloads,
        include_transcripts=True if include_transcripts else None,
        transcript_videos=transcript_videos,
    )

    llm_mode = bool(args.llm_writer) or _env_flag("NSMT_LLM_WRITER")
    review_drop = bool(args.review_drop) or _env_flag("NSMT_LLM_REVIEW_DROP")
    if llm_mode and not packet.get("media_transcripts"):
        print("Note: LLM writer is on but no transcripts are attached; the recap will use no quotes.")
    article_markdown, llm_meta = _resolve_article_markdown(packet, llm_mode=llm_mode)

    if args.dry_run:
        markdown = article_markdown
        preview_packet_path = args.packet_dir / f"mystics_postgame_{packet['game']['id']}.json"
        preview_draft_path = args.draft_dir / f"mystics-postgame-{packet['game']['date'][:10]}-{packet['game']['id']}.md"
        assets = generate_editorial_assets(packet) if args.generate_assets else None
        preview_asset_paths = _preview_asset_paths(packet, args.draft_dir / "assets") if args.generate_assets else {}
        qa_report = None
        preview_qa_path = args.draft_dir / "qa" / f"mystics-qa-{packet['game']['id']}.json"
        claim_audit = None
        preview_claim_audit_path = _preview_claim_audit_path(packet, args.draft_dir / "claim_audit")
        preview_external_path = args.draft_dir / "external_review" / f"mystics-external-review-{packet['game']['id']}.json"
        external_decision = None
        preview_external_decision_path = (
            args.draft_dir / "external_review" / f"mystics-external-editor-decision-{packet['game']['id']}.json"
        )
        if args.qa:
            qa_report = format_editorial_qa_report(
                packet,
                article_markdown=markdown,
                article_markdown_path=preview_draft_path,
                packet_path=preview_packet_path,
                assets=assets,
                asset_paths=preview_asset_paths,
            )
        if args.claim_audit:
            claim_audit = format_claim_evidence_audit(
                packet,
                article_markdown=markdown,
                article_markdown_path=preview_draft_path,
                packet_path=preview_packet_path,
                assets=assets,
                asset_paths=preview_asset_paths,
            )
        print(json.dumps(packet, indent=2, sort_keys=True))
        print("\n--- MARKDOWN DRAFT ---\n")
        print(markdown)
        if args.generate_assets:
            print("\n--- EDITORIAL ASSETS ---\n")
            print(json.dumps(assets, indent=2, sort_keys=True))
            print("\n--- ASSET INDEX ---\n")
            print(
                json.dumps(
                    format_asset_index(packet, asset_paths=preview_asset_paths),
                    indent=2,
                    sort_keys=True,
                )
            )
        if args.qa:
            print("\n--- EDITORIAL QA REPORT ---\n")
            print(json.dumps(qa_report, indent=2, sort_keys=True))
        if args.claim_audit:
            print("\n--- CLAIM EVIDENCE AUDIT ---\n")
            print(json.dumps(claim_audit, indent=2, sort_keys=True))
        if args.external_editor_packet:
            print("\n--- EXTERNAL EDITOR PACKET ---\n")
            print(
                json.dumps(
                    format_external_editor_review_packet(
                        packet,
                        article_markdown=markdown,
                        article_markdown_path=preview_draft_path,
                        assets=assets,
                        asset_paths=preview_asset_paths,
                        qa_report=qa_report,
                        qa_report_path=preview_qa_path if qa_report else None,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
        if args.ingest_external_editor_response:
            source_response = load_external_editor_response(args.ingest_external_editor_response)
            normalized_response_path = (
                args.draft_dir
                / "external_review"
                / "responses"
                / f"mystics-external-editor-response-{packet['game']['id']}.json"
            )
            normalized_response = normalize_external_editor_response(
                source_response,
                event_id=packet["game"]["id"],
                source_response_path=args.ingest_external_editor_response,
            )
            external_decision = format_external_editor_decision_summary(
                normalized_response,
                source_response_path=args.ingest_external_editor_response,
                normalized_response_path=normalized_response_path,
            )
            print("\n--- EXTERNAL EDITOR NORMALIZED RESPONSE ---\n")
            print(json.dumps(normalized_response, indent=2, sort_keys=True))
            print("\n--- EXTERNAL EDITOR DECISION SUMMARY ---\n")
            print(json.dumps(external_decision, indent=2, sort_keys=True))
        if args.discord_review:
            print("\n--- DISCORD REVIEW PACKAGE ---\n")
            print(
                json.dumps(
                    format_discord_review_package(
                        packet,
                        article_markdown_path=preview_draft_path,
                        packet_path=preview_packet_path,
                        qa_report_path=preview_qa_path if qa_report else None,
                        qa_report=qa_report,
                        claim_audit_path=preview_claim_audit_path if claim_audit else None,
                        claim_audit=claim_audit,
                        external_editor_packet_path=preview_external_path if args.external_editor_packet else None,
                        external_editor_decision_path=preview_external_decision_path if external_decision else None,
                        external_editor_decision=external_decision,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
        return 0

    response_ingest_only = bool(args.ingest_external_editor_response) and not any(
        [args.generate_assets, args.qa, args.claim_audit, args.external_editor_packet]
    )
    if response_ingest_only:
        game = packet["game"]
        packet_path = args.packet_dir / f"mystics_postgame_{game['id']}.json"
        draft_path = args.draft_dir / f"mystics-postgame-{game['date'][:10]}-{game['id']}.md"
        print("Skipped packet/draft writes for external editor response ingestion.")
    else:
        packet_path, draft_path = write_outputs(
            packet, packet_dir=args.packet_dir, draft_dir=args.draft_dir, article_markdown=article_markdown
        )
        print(f"Wrote normalized packet: {_display_path(packet_path)}")
        print(f"Wrote markdown draft: {_display_path(draft_path)} [{llm_meta['writer']}]")
        _write_quote_review_sidecar(packet, llm_meta, args.draft_dir / "external_review")
    assets = None
    asset_paths: dict[str, Path] = {}
    if args.generate_assets:
        assets = generate_editorial_assets(packet)
        asset_paths, index_path = write_editorial_assets(packet, asset_dir=args.draft_dir / "assets", assets=assets)
        for asset_key, asset_path in asset_paths.items():
            print(f"Wrote {asset_key.replace('_', ' ')} asset: {_display_path(asset_path)}")
        print(f"Wrote asset index: {_display_path(index_path)}")
    qa_path = None
    qa_report = None
    if args.qa:
        qa_path = write_editorial_qa_report(
            packet,
            article_markdown_path=draft_path,
            packet_path=packet_path,
            qa_dir=args.draft_dir / "qa",
            assets=assets,
            asset_paths=asset_paths,
        )
        qa_report = json.loads(qa_path.read_text())
        print(f"Wrote editorial QA report: {_display_path(qa_path)}")
    claim_audit_path = None
    claim_audit = None
    if args.claim_audit:
        claim_audit_path = write_claim_evidence_audit(
            packet,
            article_markdown_path=draft_path,
            packet_path=packet_path,
            audit_dir=args.draft_dir / "claim_audit",
            assets=assets,
            asset_paths=asset_paths,
        )
        claim_audit = load_claim_evidence_audit(claim_audit_path, event_id=packet["game"]["id"])
        print(f"Wrote claim evidence audit: {_display_path(claim_audit_path)}")
    external_editor_packet_path = None
    if args.external_editor_packet:
        external_editor_packet_path = write_external_editor_review_packet(
            packet,
            article_markdown_path=draft_path,
            external_review_dir=args.draft_dir / "external_review",
            assets=assets,
            asset_paths=asset_paths,
            qa_report=qa_report,
            qa_report_path=qa_path,
        )
        print(f"Wrote external editor packet: {_display_path(external_editor_packet_path)}")
    external_editor_decision_path = None
    external_editor_decision = None
    if args.ingest_external_editor_response:
        _, external_editor_decision_path = ingest_external_editor_response(
            packet,
            source_response_path=args.ingest_external_editor_response,
            external_review_dir=args.draft_dir / "external_review",
        )
        external_editor_decision = json.loads(external_editor_decision_path.read_text())
        normalized_response_path = Path(external_editor_decision["normalized_response_path"])
        print(f"Wrote normalized external editor response: {_display_path(normalized_response_path)}")
        print(f"Wrote external editor decision summary: {_display_path(external_editor_decision_path)}")
    if review_drop and llm_mode and not response_ingest_only:
        _post_llm_review_drop(packet, llm_meta, args.draft_dir / "external_review")
    if args.discord_review:
        review_path = write_discord_review_package(
            packet,
            article_markdown_path=draft_path,
            packet_path=packet_path,
            review_dir=args.draft_dir / "review",
            qa_report_path=qa_path,
            qa_report=qa_report,
            claim_audit_path=claim_audit_path,
            claim_audit=claim_audit,
            external_editor_packet_path=external_editor_packet_path,
            external_editor_decision_path=external_editor_decision_path,
            external_editor_decision=external_editor_decision,
        )
        print(f"Wrote Discord review package: {_display_path(review_path)}")
    print("Publish step intentionally skipped.")
    return 0


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from exc


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _parse_transcript_videos(values: list[str] | None) -> list[dict[str, str]] | None:
    parsed: list[dict[str, str]] = []
    for value in values or []:
        if ":" not in value:
            print(f"Ignoring --transcript-video {value!r}; expected VIDEO_ID:KIND.")
            continue
        video_id, kind = value.split(":", 1)
        video_id, kind = video_id.strip(), kind.strip().lower()
        if video_id and kind:
            parsed.append({"video_id": video_id, "kind": kind})
    return parsed or None


def _resolve_article_markdown(packet: dict, *, llm_mode: bool) -> tuple[str, dict]:
    """Produce the recap markdown.

    LLM writer when on, with a deterministic fallback on API failure or an
    unsalvageable quote hard-fail; the deterministic render otherwise. The
    deterministic path is always available as the fallback + comparison baseline.
    """
    from newsroom.drafts import render_markdown_document, render_markdown_draft

    meta: dict = {
        "llm_used": False,
        "writer": "deterministic",
        "reason": None,
        "quote_verification": None,
        "usage": None,
        "model": None,
    }
    if not llm_mode:
        return render_markdown_draft(packet), meta

    try:
        from newsroom.llm_writer import write_recap

        recap = write_recap(packet, writer_profile=packet.get("writer_profile"))
    except Exception as exc:  # any API / config failure -> deterministic fallback
        print(f"LLM writer unavailable ({type(exc).__name__}: {exc}). Falling back to deterministic draft.")
        meta["reason"] = f"llm_error: {exc}"
        return render_markdown_draft(packet), meta

    quote_verification = recap.get("quote_verification") or {}
    meta.update(
        {
            "quote_verification": quote_verification,
            "usage": recap.get("usage"),
            "model": recap.get("model"),
        }
    )

    if quote_verification.get("hard_fail"):
        print(
            f"LLM recap FAILED quote verification: {quote_verification.get('unverified_count')} "
            "unverified quote(s). Falling back to deterministic draft."
        )
        for quote in quote_verification.get("unverified_quotes", []):
            print(f"  unverified (ratio {quote['match_ratio']}): {quote['text']!r}")
        meta["reason"] = "quote_hard_fail"
        return render_markdown_draft(packet), meta

    from newsroom.claim_audit import validate_person_names

    name_validation = validate_person_names(packet, recap["body"])
    meta["name_validation"] = name_validation
    if name_validation.get("hard_fail"):
        print("LLM recap FAILED name validation (wrong or invented coach name). Falling back to deterministic draft.")
        for flag in name_validation.get("flagged_names", []):
            print(f"  bio error [{flag['context']}]: {flag['name']} - {flag['reason']}")
        meta["reason"] = "name_hard_fail"
        return render_markdown_draft(packet), meta

    markdown = render_markdown_document(
        packet, headline=recap["headline"], article=recap["body"], excerpt=recap["excerpt"]
    )
    meta.update(
        {
            "llm_used": True,
            "writer": f"llm:{recap.get('model')}",
            "headline": recap["headline"],
            "body": recap["body"],
            "excerpt": recap["excerpt"],
        }
    )

    attributed = quote_verification.get("attributed_quotes") or []
    if attributed:
        print(
            f"MANDATORY EXTERNAL REVIEW: {len(attributed)} speaker-attributed quote(s) "
            "require human verification before publish:"
        )
        for quote in attributed:
            print(f"  [{quote.get('speaker')}] {quote['text']!r}")
    name_flags = name_validation.get("flagged_names") or []
    if name_flags:
        print(f"NAME REVIEW: {len(name_flags)} unverified person name(s) flagged for human check:")
        for flag in name_flags:
            print(f"  [{flag['context']}] {flag['name']} - {flag['reason']}")
    return markdown, meta


def _write_quote_review_sidecar(packet: dict, llm_meta: dict, external_review_dir: Path) -> None:
    """Route the LLM recap's quote verification into the external_review area for
    mandatory human review before any publish step. No-op for the deterministic path."""
    quote_verification = llm_meta.get("quote_verification")
    if not llm_meta.get("llm_used") or not quote_verification:
        return
    external_review_dir.mkdir(parents=True, exist_ok=True)
    event_id = packet["game"]["id"]
    sidecar = {
        "schema_version": "mystics-quote-review/v0.1",
        "event_id": event_id,
        "writer": llm_meta.get("writer"),
        "human_editor_required": True,
        "no_auto_publish": True,
        "quote_verification": quote_verification,
        "name_validation": llm_meta.get("name_validation"),
    }
    path = external_review_dir / f"mystics-quote-review-{event_id}.json"
    path.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n")
    print(f"Wrote quote review (mandatory human review): {_display_path(path)}")


def _format_quote_links(quote_verification: dict) -> str:
    """One line per verified quote: timestamp, speaker, text, and YouTube deep link."""
    lines = []
    for quote in (quote_verification or {}).get("quotes", []):
        if not quote.get("verified") or not quote.get("source_link"):
            continue
        speaker = quote.get("speaker") or "unattributed"
        lines.append(
            f'[{quote.get("timestamp", "00:00")}] {speaker}: "{quote.get("text", "")}" -> {quote["source_link"]}'
        )
    return "\n".join(lines)


def _post_llm_review_drop(packet: dict, llm_meta: dict, external_review_dir: Path) -> None:
    """Run the Codex fact-check on the LLM recap and post a REVIEW drop to the
    Mystics Discord channel via the existing proxy.

    Human-gated review artifact, NOT a live publish: no admin/site save happens
    here. Lazy imports keep the deterministic path + tests free of
    generate_content / requests / the codex CLI. Never raises.
    """
    if not llm_meta.get("llm_used"):
        print("Review drop skipped: deterministic fallback in use (no LLM recap to drop).")
        return
    headline = llm_meta.get("headline") or "Mystics recap"
    body = llm_meta.get("body") or ""
    quote_verification = llm_meta.get("quote_verification") or {}
    final_score = (packet.get("narrative") or {}).get("final_score", "")
    game = packet.get("game") or {}

    team = None
    verdict, report = "UNKNOWN", "(codex fact-check not run)"
    # (a) Codex fact-check (Mac-side, ChatGPT auth). Failure never blocks the drop.
    try:
        from scripts.codex_review import extract_verdict, review_with_codex
        from generate_content import ALL_TEAMS, load_team_kb

        team = next((t for t in ALL_TEAMS if t["name"] == "Washington Mystics"), None)
        kb = load_team_kb(team) if team else {}
        report = review_with_codex({"title": headline, "body": body}, team or {"name": "Washington Mystics"}, kb, packet)
        verdict = extract_verdict(report)
        print(f"Codex fact-check verdict: {verdict}")
    except Exception as exc:  # noqa: BLE001 - review drop must survive a codex failure
        print(f"Codex fact-check unavailable ({type(exc).__name__}: {exc}); review drop will show UNKNOWN verdict.")

    # Persist the Codex verdict + FULL report so the reasoning survives even if the
    # Discord post fails or gets truncated.
    try:
        external_review_dir.mkdir(parents=True, exist_ok=True)
        codex_path = external_review_dir / f"mystics-codex-review-{game.get('id', 'unknown')}.md"
        codex_path.write_text(
            f"# Codex fact-check - Mystics {game.get('id', '')}\n\n"
            f"Verdict: {verdict}\n\nhuman_editor_required: true\n\n---\n\n{report}\n"
        )
        print(f"Wrote Codex fact-check: {_display_path(codex_path)} (verdict {verdict})")
    except OSError as exc:
        print(f"Could not write Codex review sidecar ({exc}).")

    # (b) Discord review drop via the existing proxy. No public-site save.
    try:
        from generate_content import post_recap_to_discord

        if team is None:
            from generate_content import ALL_TEAMS

            team = next((t for t in ALL_TEAMS if t["name"] == "Washington Mystics"), None)
    except Exception as exc:  # noqa: BLE001
        print(f"Discord review drop aborted: cannot import proxy ({exc}).")
        return
    if team is None:
        print("Discord review drop aborted: Mystics team entry not found.")
        return

    # Discord sums ALL embed text in a message against a 6000-char cap. Bound the
    # body (article embed) and the Codex report (fact-check embed) so both fit; the
    # full recap is in the repo draft and the full Codex report in the sidecar above.
    quote_links = _format_quote_links(quote_verification)
    core = body
    if quote_links:
        core += "\n\nVerified quotes (transcript timestamps):\n" + quote_links
    if len(core) > 2800:
        core = core[:2800].rstrip() + " [...]"
    discord_body = core + (
        "\n\nLLM REVIEW DROP. Human editor approval required before publish. "
        "Not saved to the public site (review only). Full draft + Codex report in the repo."
    )
    report_for_discord = (
        report if len(report) <= 1900 else report[:1900].rstrip() + " [...truncated; full report in the Codex sidecar]"
    )
    summary = {"score": final_score}
    try:
        game_date = _parse_date(str(game.get("date", ""))[:10])
    except (argparse.ArgumentTypeError, ValueError):
        game_date = date.today()
    posted = post_recap_to_discord(
        f"[REVIEW] {final_score} | Mystics LLM Recap",
        discord_body,
        team,
        summary,
        game_date,
        fact_verdict=verdict,
        fact_report=report_for_discord,
    )
    print(
        f"Discord review drop posted={posted} (channel_target={team.get('channel_target')}). "
        "human_editor_required=True; not published to the public site."
    )


if __name__ == "__main__":
    raise SystemExit(main())
