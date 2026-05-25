"""External editor packet and response handling for Mystics recaps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ingestion.cache import iso_utc
from newsroom.common import DEFAULT_EXTERNAL_REVIEW_DIR, EXTERNAL_EDITOR_PROMPT_PATH, PROJECT_ROOT, _display_path, _editorial_rules, _load_assets_from_paths
from newsroom.drafts import render_markdown_draft
from newsroom.memory import _external_memory_context_summary
from newsroom.schemas import (
    EXTERNAL_EDITOR_RESPONSE_FIELDS,
    EXTERNAL_EDITOR_VERDICTS,
    validate_external_editor_decision_summary,
    validate_external_editor_packet,
    validate_external_editor_response as _validate_external_editor_response,
    validate_normalized_external_editor_response,
    validate_qa_report,
)

def load_external_editor_prompt(path: Path | str = EXTERNAL_EDITOR_PROMPT_PATH) -> str:
    """Load the external editor prompt template."""
    prompt_path = Path(path)
    if not prompt_path.is_absolute():
        prompt_path = PROJECT_ROOT / prompt_path
    return prompt_path.read_text()


def format_external_editor_review_packet(
    packet: dict[str, Any],
    *,
    article_markdown: str | None = None,
    article_markdown_path: Path | str | None = None,
    assets: dict[str, Any] | None = None,
    asset_paths: dict[str, Path | str] | None = None,
    qa_report: dict[str, Any] | None = None,
    qa_report_path: Path | str | None = None,
    editor_prompt: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a local packet for a future external editor model review."""
    if article_markdown is None and article_markdown_path and Path(article_markdown_path).exists():
        article_markdown = Path(article_markdown_path).read_text()
    article_markdown = article_markdown or render_markdown_draft(packet)

    asset_paths = asset_paths or {}
    if assets is None and asset_paths:
        assets = _load_assets_from_paths(asset_paths)
    assets = assets or {}

    if qa_report is None and qa_report_path and Path(qa_report_path).exists():
        qa_report = _load_validated_qa_report(qa_report_path, event_id=str(packet["game"]["id"]))
    elif qa_report is not None:
        _validate_qa_report_for_event(qa_report, qa_report_path, str(packet["game"]["id"]))

    review_packet = {
        "schema_version": "mystics-external-editor-review/v0.1",
        "editor_prompt": editor_prompt or load_external_editor_prompt(),
        "main_article_markdown": article_markdown,
        "generated_assets": assets,
        "normalized_game_packet_summary": _external_game_packet_summary(packet),
        "story_angles": packet.get("story_angles") or [],
        "memory_context_summary": _external_memory_context_summary(packet),
        "internal_qa_summary": _external_qa_summary(qa_report, qa_report_path=qa_report_path),
        "editorial_rules": _editorial_rules(packet),
        "source_event_id": packet["game"]["id"],
        "generated_timestamp": generated_at or iso_utc(),
        "source_paths": {
            "article_markdown_path": _display_path(article_markdown_path) if article_markdown_path else None,
            "asset_paths": {key: _display_path(path) for key, path in sorted(asset_paths.items())},
            "qa_report_path": _display_path(qa_report_path) if qa_report_path else None,
        },
        "external_review_only": True,
        "no_auto_publish": True,
        "no_auto_rewrite": True,
    }
    return validate_external_editor_packet(review_packet)


def write_external_editor_review_packet(
    packet: dict[str, Any],
    *,
    article_markdown_path: Path | str,
    external_review_dir: Path = DEFAULT_EXTERNAL_REVIEW_DIR,
    assets: dict[str, Any] | None = None,
    asset_paths: dict[str, Path | str] | None = None,
    qa_report: dict[str, Any] | None = None,
    qa_report_path: Path | str | None = None,
    generated_at: str | None = None,
) -> Path:
    """Write a local external-editor review packet. This does not call an LLM."""
    external_review_dir.mkdir(parents=True, exist_ok=True)
    event_id = packet["game"]["id"]
    review_path = external_review_dir / f"mystics-external-review-{event_id}.json"
    review_packet = format_external_editor_review_packet(
        packet,
        article_markdown_path=article_markdown_path,
        assets=assets,
        asset_paths=asset_paths,
        qa_report=qa_report,
        qa_report_path=qa_report_path,
        generated_at=generated_at,
    )
    review_path.write_text(json.dumps(review_packet, indent=2, sort_keys=True) + "\n")
    return review_path


def load_external_editor_response(path: Path | str) -> dict[str, Any]:
    """Load an external editor JSON response from disk."""
    response_path = Path(path)
    if not response_path.is_absolute():
        response_path = PROJECT_ROOT / response_path
    return validate_external_editor_response(json.loads(response_path.read_text()))


def validate_external_editor_response(response: dict[str, Any]) -> dict[str, Any]:
    """Validate an external editor response without applying any edits."""
    return _validate_external_editor_response(response)


def normalize_external_editor_response(
    response: dict[str, Any],
    *,
    event_id: str,
    source_response_path: Path | str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Return a validated, normalized external editor response envelope."""
    validate_external_editor_response(response)
    normalized = {field: response[field] for field in EXTERNAL_EDITOR_RESPONSE_FIELDS}
    normalized["confidence"] = float(normalized["confidence"])
    envelope = {
        "schema_version": "mystics-external-editor-response/v0.1",
        "event_id": str(event_id),
        "source_response_path": _display_path(source_response_path),
        "generated_timestamp": generated_at or iso_utc(),
        "response": normalized,
        "advisory_only": True,
        "human_editor_required": True,
        "no_auto_publish": True,
        "no_auto_rewrite": True,
    }
    return validate_normalized_external_editor_response(envelope)


def format_external_editor_decision_summary(
    normalized_response: dict[str, Any],
    *,
    source_response_path: Path | str,
    normalized_response_path: Path | str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Summarize an external editor response for review workflow handoff."""
    validate_normalized_external_editor_response(normalized_response)
    response = normalized_response.get("response") or {}
    validate_external_editor_response(response)
    verdict = response["overall_verdict"]
    publish_blockers = response["publish_blockers"]
    unsupported_claims = response["unsupported_claims"]
    recommended_edits = response["recommended_edits"]
    needs_revision = verdict in {"needs_revision", "reject"}
    safe_to_publish_candidate = verdict in {"approve", "approve_with_minor_edits"} and len(publish_blockers) == 0

    summary = {
        "schema_version": "mystics-external-editor-decision/v0.1",
        "event_id": normalized_response.get("event_id"),
        "source_response_path": _display_path(source_response_path),
        "normalized_response_path": _display_path(normalized_response_path),
        "overall_verdict": verdict,
        "confidence": float(response["confidence"]),
        "publish_blockers_count": len(publish_blockers),
        "unsupported_claims_count": len(unsupported_claims),
        "recommended_edits_count": len(recommended_edits),
        "needs_revision": needs_revision,
        "safe_to_publish_candidate": safe_to_publish_candidate,
        "human_editor_required": True,
        "generated_timestamp": generated_at or iso_utc(),
        "advisory_only": True,
        "no_auto_publish": True,
        "no_auto_rewrite": True,
    }
    return validate_external_editor_decision_summary(summary)


def ingest_external_editor_response(
    packet: dict[str, Any],
    *,
    source_response_path: Path | str,
    external_review_dir: Path = DEFAULT_EXTERNAL_REVIEW_DIR,
    generated_at: str | None = None,
) -> tuple[Path, Path]:
    """Validate and store an external editor response. This never rewrites drafts."""
    response = load_external_editor_response(source_response_path)
    event_id = packet["game"]["id"]
    response_dir = external_review_dir / "responses"
    response_dir.mkdir(parents=True, exist_ok=True)
    external_review_dir.mkdir(parents=True, exist_ok=True)

    normalized_path = response_dir / f"mystics-external-editor-response-{event_id}.json"
    normalized = normalize_external_editor_response(
        response,
        event_id=event_id,
        source_response_path=source_response_path,
        generated_at=generated_at,
    )
    normalized_path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n")

    decision_path = external_review_dir / f"mystics-external-editor-decision-{event_id}.json"
    decision = format_external_editor_decision_summary(
        normalized,
        source_response_path=source_response_path,
        normalized_response_path=normalized_path,
        generated_at=generated_at,
    )
    decision_path.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n")
    return normalized_path, decision_path


def _external_game_packet_summary(packet: dict[str, Any]) -> dict[str, Any]:
    game = packet["game"]
    narrative = packet.get("narrative") or {}
    teams = game.get("teams") or []
    return {
        "event_id": game.get("id"),
        "date": game.get("date"),
        "venue": game.get("venue"),
        "status": game.get("status"),
        "final_score": narrative.get("final_score"),
        "result": narrative.get("result"),
        "teams": [
            {
                "id": team.get("id"),
                "name": team.get("name"),
                "abbreviation": team.get("abbreviation"),
                "home_away": team.get("home_away"),
                "score": team.get("score"),
                "winner": team.get("winner"),
                "team_stats": team.get("team_stats"),
            }
            for team in teams
        ],
        "scoring_by_quarter": game.get("scoring_by_quarter") or [],
        "top_performers": narrative.get("top_performers") or [],
        "biggest_scoring_run": narrative.get("biggest_scoring_run") or {},
        "key_quarter_or_turning_point": narrative.get("key_quarter_or_turning_point") or {},
        "stat_edges": narrative.get("stat_edges") or {},
        "play_by_play_available": bool((game.get("play_by_play") or {}).get("available")),
        "sources": packet.get("sources") or [],
    }


def _external_qa_summary(
    qa_report: dict[str, Any] | None,
    *,
    qa_report_path: Path | str | None = None,
) -> dict[str, Any]:
    if not qa_report:
        return {
            "available": False,
            "qa_report_path": _display_path(qa_report_path) if qa_report_path else None,
        }
    return {
        "available": True,
        "qa_report_path": _display_path(qa_report_path) if qa_report_path else qa_report.get("qa_report_path"),
        "overall_recommendation": qa_report.get("overall_recommendation"),
        "summary": qa_report.get("summary") or {},
        "item_reports": qa_report.get("item_reports") or {},
        "advisory_only": qa_report.get("advisory_only", True),
    }


def _load_validated_qa_report(path: Path | str, *, event_id: str) -> dict[str, Any]:
    path_obj = Path(path)
    try:
        payload = json.loads(path_obj.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read QA report at {path_obj}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid QA report at {path_obj}: artifact must be a JSON object")
    return _validate_qa_report_for_event(payload, path, event_id)


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
    actual_event_id = str(qa_report.get("event_id") or "")
    if actual_event_id != event_id:
        location = Path(path) if path else "provided QA report"
        raise ValueError(
            f"QA report at {location} has event_id {actual_event_id!r}; "
            f"expected active packet event_id {event_id!r}"
        )
    return qa_report
