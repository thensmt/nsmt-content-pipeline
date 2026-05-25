"""Discord-ready local review package generation for Mystics recaps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from newsroom.claim_audit import load_claim_evidence_audit
from newsroom.common import DEFAULT_REVIEW_DIR, _dedupe_strings, _display_path, _opponent_team, _review_top_performers, _risk_summary, _selected_angle
from newsroom.schemas import (
    validate_claim_evidence_audit,
    validate_discord_review_package,
    validate_external_editor_decision_summary,
    validate_external_editor_packet,
    validate_qa_report,
)

EDITOR_CHECKLIST = [
    "Verify final score",
    "Verify player stats",
    "Check selected angle",
    "Remove unsupported claims",
    "Confirm no fake quotes",
    "Confirm headline fits NSMT voice",
    "Approve for Contentful draft creation",
]

def format_discord_review_package(
    packet: dict[str, Any],
    *,
    article_markdown_path: Path | str,
    packet_path: Path | str,
    qa_report_path: Path | str | None = None,
    qa_report: dict[str, Any] | None = None,
    claim_audit_path: Path | str | None = None,
    claim_audit: dict[str, Any] | None = None,
    external_editor_packet_path: Path | str | None = None,
    external_editor_decision_path: Path | str | None = None,
    external_editor_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a Discord-ready review payload. This does not post anywhere."""
    game = packet["game"]
    event_id = str(game["id"])
    narrative = packet["narrative"]
    opponent = _opponent_team(game["teams"])
    selected = _selected_angle(packet)
    alternates = (packet.get("story_angles") or [])[1:]
    article_path = _display_path(article_markdown_path)
    normalized_packet_path = _display_path(packet_path)
    risk_flags = _dedupe_strings(list(selected.get("risk_flags") or []))
    top_performers = _review_top_performers(narrative.get("top_performers") or [])
    qa_lines: list[str] = []
    if qa_report_path and qa_report:
        qa_lines = [
            f"QA report path: {_display_path(qa_report_path)}",
            f"QA recommendation: {qa_report.get('overall_recommendation', 'Unavailable')}",
        ]
    claim_audit_lines: list[str] = []
    if claim_audit_path and claim_audit:
        summary = claim_audit.get("summary") or {}
        sentence_summary = claim_audit.get("sentence_summary") or {}
        claim_audit_lines = [
            f"Claim audit path: {_display_path(claim_audit_path)}",
            f"Claim audit warnings: {summary.get('warning_count', 'Unavailable')}",
        ]
        if sentence_summary:
            claim_audit_lines.extend(
                [
                    f"Claim grounding unsupported sentences: {sentence_summary.get('unsupported_sentence_count', 'Unavailable')}",
                    f"Claim grounding weak sentences: {sentence_summary.get('weak_sentence_count', 'Unavailable')}",
                    f"Claim grounding contradictions: {sentence_summary.get('contradiction_count', 'Unavailable')}",
                    "Claim grounding lowest confidence IDs: "
                    f"{', '.join(sentence_summary.get('lowest_confidence_sentence_ids') or []) or 'None'}",
                ]
            )
    external_lines = []
    if external_editor_packet_path:
        external_lines = [f"External editor packet: {_display_path(external_editor_packet_path)}"]
    decision_lines = []
    if external_editor_decision_path and external_editor_decision:
        decision_lines = [
            f"External editor decision: {_display_path(external_editor_decision_path)}",
            f"External editor verdict: {external_editor_decision.get('overall_verdict', 'Unavailable')}",
        ]

    summary_message = "\n".join(
        [
            f"Final score: {narrative.get('final_score', 'Unavailable')}",
            f"Top-ranked story angle: {selected.get('angle_title', 'Unavailable')}",
            f"Top performers: {top_performers or 'Unavailable'}",
            f"Biggest risk flags: {_risk_summary(risk_flags)}",
            f"Draft path: {article_path}",
            f"Packet path: {normalized_packet_path}",
            *qa_lines,
            *claim_audit_lines,
            *external_lines,
            *decision_lines,
            "Human review required before publishing.",
        ]
    )

    package = {
        "thread_title": f"[Mystics Recap] {opponent['name']} vs Washington - {game['date'][:10]} - {game['id']}",
        "summary_message": summary_message,
        "editor_checklist": list(EDITOR_CHECKLIST),
        "article_markdown_path": article_path,
        "packet_path": normalized_packet_path,
        "risk_flags": risk_flags,
        "selected_angle": selected,
        "alternate_angles": alternates,
        "recommended_status": "human_review_required",
    }
    if qa_report_path and qa_report:
        _validate_qa_report_for_event(qa_report, qa_report_path, event_id)
        package.update(
            {
                "qa_report_path": _display_path(qa_report_path),
                "overall_recommendation": qa_report.get("overall_recommendation"),
                "lowest_scoring_items": (qa_report.get("summary") or {}).get("lowest_scoring_items", []),
                "top_issue_flags": (qa_report.get("summary") or {}).get("top_issue_flags", []),
            }
        )
    if claim_audit_path and claim_audit:
        _validate_claim_audit_for_event(claim_audit, claim_audit_path, event_id)
        package.update(
            {
                "claim_audit_path": _display_path(claim_audit_path),
                "claim_audit_summary": _claim_audit_review_summary(claim_audit),
            }
        )
    if external_editor_packet_path:
        package.update(
            {
                "external_editor_packet_path": _display_path(external_editor_packet_path),
                "recommended_external_review": True,
            }
        )
    if external_editor_decision_path and external_editor_decision:
        _validate_external_decision_for_event(external_editor_decision, external_editor_decision_path, event_id)
        package.update(
            {
                "external_editor_decision_path": _display_path(external_editor_decision_path),
                "external_editor_verdict": external_editor_decision.get("overall_verdict"),
                "external_editor_confidence": external_editor_decision.get("confidence"),
                "external_editor_publish_blockers_count": external_editor_decision.get("publish_blockers_count"),
                "external_editor_needs_revision": external_editor_decision.get("needs_revision"),
                "human_editor_required": True,
            }
        )
    return validate_discord_review_package(package)


def write_discord_review_package(
    packet: dict[str, Any],
    *,
    article_markdown_path: Path | str,
    packet_path: Path | str,
    review_dir: Path = DEFAULT_REVIEW_DIR,
    qa_report_path: Path | str | None = None,
    qa_report: dict[str, Any] | None = None,
    claim_audit_path: Path | str | None = None,
    claim_audit: dict[str, Any] | None = None,
    external_editor_packet_path: Path | str | None = None,
    external_editor_decision_path: Path | str | None = None,
    external_editor_decision: dict[str, Any] | None = None,
) -> Path:
    review_dir.mkdir(parents=True, exist_ok=True)
    game = packet["game"]
    review_path = review_dir / f"mystics-postgame-{game['date'][:10]}-{game['id']}-review.json"
    if qa_report_path is None:
        candidate = review_dir.parent / "qa" / f"mystics-qa-{game['id']}.json"
        if candidate.exists():
            qa_report_path = candidate
    if qa_report is None and qa_report_path and Path(qa_report_path).exists():
        qa_report = _load_validated_qa_report(qa_report_path, event_id=str(game["id"]))
    if qa_report is not None:
        _validate_qa_report_for_event(qa_report, qa_report_path, str(game["id"]))
    if claim_audit_path is None:
        candidate = review_dir.parent / "claim_audit" / f"mystics-claim-audit-{game['id']}.json"
        if candidate.exists():
            claim_audit_path = candidate
    if claim_audit is None and claim_audit_path and Path(claim_audit_path).exists():
        claim_audit = load_claim_evidence_audit(claim_audit_path, event_id=str(game["id"]))
    if claim_audit is not None:
        _validate_claim_audit_for_event(claim_audit, claim_audit_path, str(game["id"]))
    if external_editor_packet_path is None:
        candidate = review_dir.parent / "external_review" / f"mystics-external-review-{game['id']}.json"
        if candidate.exists():
            external_editor_packet_path = candidate
    if external_editor_packet_path and Path(external_editor_packet_path).exists():
        _load_validated_external_editor_packet(external_editor_packet_path, event_id=str(game["id"]))
    if external_editor_decision_path is None:
        candidate = review_dir.parent / "external_review" / f"mystics-external-editor-decision-{game['id']}.json"
        if candidate.exists():
            external_editor_decision_path = candidate
    if external_editor_decision is None and external_editor_decision_path and Path(external_editor_decision_path).exists():
        external_editor_decision = _load_validated_external_decision(
            external_editor_decision_path,
            event_id=str(game["id"]),
        )
    if external_editor_decision is not None:
        _validate_external_decision_for_event(external_editor_decision, external_editor_decision_path, str(game["id"]))
    package = format_discord_review_package(
        packet,
        article_markdown_path=article_markdown_path,
        packet_path=packet_path,
        qa_report_path=qa_report_path,
        qa_report=qa_report,
        claim_audit_path=claim_audit_path,
        claim_audit=claim_audit,
        external_editor_packet_path=external_editor_packet_path,
        external_editor_decision_path=external_editor_decision_path,
        external_editor_decision=external_editor_decision,
    )
    review_path.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n")
    return review_path


def _load_json_artifact(path: Path | str, label: str) -> dict[str, Any]:
    path_obj = Path(path)
    try:
        payload = json.loads(path_obj.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read {label} at {path_obj}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid {label} at {path_obj}: artifact must be a JSON object")
    return payload


def _load_validated_qa_report(path: Path | str, *, event_id: str) -> dict[str, Any]:
    payload = _load_json_artifact(path, "QA report")
    return _validate_qa_report_for_event(payload, path, event_id)


def _load_validated_external_editor_packet(path: Path | str, *, event_id: str) -> dict[str, Any]:
    payload = _load_json_artifact(path, "external editor packet")
    try:
        validate_external_editor_packet(payload)
    except ValueError as exc:
        raise ValueError(f"Invalid external editor packet at {Path(path)}: {exc}") from exc
    _require_artifact_event_match(
        payload,
        field="source_event_id",
        expected_event_id=event_id,
        label="external editor packet",
        path=path,
    )
    return payload


def _load_validated_external_decision(path: Path | str, *, event_id: str) -> dict[str, Any]:
    payload = _load_json_artifact(path, "external editor decision summary")
    return _validate_external_decision_for_event(payload, path, event_id)


def _validate_qa_report_for_event(
    qa_report: dict[str, Any],
    path: Path | str | None,
    event_id: str,
) -> dict[str, Any]:
    try:
        validate_qa_report(qa_report)
    except ValueError as exc:
        location = Path(path) if path else "provided QA report"
        raise ValueError(f"Invalid QA report at {location}: {exc}") from exc
    _require_artifact_event_match(
        qa_report,
        field="event_id",
        expected_event_id=event_id,
        label="QA report",
        path=path,
    )
    return qa_report


def _validate_external_decision_for_event(
    decision: dict[str, Any],
    path: Path | str | None,
    event_id: str,
) -> dict[str, Any]:
    try:
        validate_external_editor_decision_summary(decision)
    except ValueError as exc:
        location = Path(path) if path else "provided external editor decision summary"
        raise ValueError(f"Invalid external editor decision summary at {location}: {exc}") from exc
    _require_artifact_event_match(
        decision,
        field="event_id",
        expected_event_id=event_id,
        label="external editor decision summary",
        path=path,
    )
    return decision


def _validate_claim_audit_for_event(
    claim_audit: dict[str, Any],
    path: Path | str | None,
    event_id: str,
) -> dict[str, Any]:
    location = Path(path) if path else "provided claim evidence audit"
    try:
        validate_claim_evidence_audit(claim_audit)
    except ValueError as exc:
        raise ValueError(f"Invalid claim evidence audit at {location}: {exc}") from exc
    actual_event_id = str(claim_audit.get("event_id") or "")
    if actual_event_id != event_id:
        raise ValueError(
            f"claim evidence audit at {location} has event_id {actual_event_id!r}; "
            f"expected active packet event_id {event_id!r}"
        )
    return claim_audit


def _claim_audit_review_summary(claim_audit: dict[str, Any]) -> dict[str, Any]:
    summary = claim_audit.get("summary") or {}
    review_summary = {
        "total_claims": summary.get("total_claims", 0),
        "category_counts": summary.get("category_counts", {}),
        "warning_count": summary.get("warning_count", 0),
        "second_source_present": summary.get("second_source_present", False),
    }
    sentence_summary = claim_audit.get("sentence_summary") or {}
    if sentence_summary:
        review_summary.update(
            {
                "unsupported_sentence_count": sentence_summary.get("unsupported_sentence_count", 0),
                "weak_sentence_count": sentence_summary.get("weak_sentence_count", 0),
                "contradiction_count": sentence_summary.get("contradiction_count", 0),
                "lowest_confidence_sentence_ids": sentence_summary.get("lowest_confidence_sentence_ids", []),
            }
        )
    return review_summary


def _require_artifact_event_match(
    artifact: dict[str, Any],
    *,
    field: str,
    expected_event_id: str,
    label: str,
    path: Path | str | None,
) -> None:
    actual_event_id = str(artifact.get(field) or "")
    if actual_event_id != expected_event_id:
        location = Path(path) if path else f"provided {label}"
        raise ValueError(
            f"{label} at {location} has {field} {actual_event_id!r}; "
            f"expected active packet event_id {expected_event_id!r}"
        )
