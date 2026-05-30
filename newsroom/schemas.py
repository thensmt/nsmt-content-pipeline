"""Plain-Python validation boundaries for Mystics editorial artifacts."""

from __future__ import annotations

from typing import Any

QA_SCORE_CATEGORIES = [
    "factual_safety",
    "source_support",
    "clarity",
    "nsmt_voice_fit",
    "repetition_risk",
    "unsupported_claim_risk",
    "publish_readiness",
]

QA_RECOMMENDATIONS = [
    "approve_for_editor_review",
    "needs_human_revision",
    "reject_and_regenerate",
]

QA_ISSUE_FLAGS = [
    "missing_score",
    "missing_opponent",
    "missing_top_performers",
    "unsupported_causality",
    "fake_quote_risk",
    "too_generic",
    "too_clickbaity",
    "too_long",
    "too_short",
    "headline_weak",
    "social_caption_weak",
    "memory_overreach",
    "unverified_name",
]

EXTERNAL_EDITOR_VERDICTS = [
    "approve",
    "approve_with_minor_edits",
    "needs_revision",
    "reject",
]

EXTERNAL_EDITOR_RESPONSE_FIELDS = [
    "overall_verdict",
    "article_notes",
    "asset_notes",
    "factual_risks",
    "unsupported_claims",
    "headline_feedback",
    "voice_feedback",
    "recommended_edits",
    "suggested_headline",
    "publish_blockers",
    "confidence",
]

CLAIM_AUDIT_CATEGORIES = [
    "supported_by_packet",
    "supported_by_memory",
    "unsupported",
    "needs_human_review",
    "balance_warning",
    "source_gap",
]

CLAIM_AUDIT_WARNING_CATEGORIES = [
    "unsupported",
    "needs_human_review",
    "balance_warning",
    "source_gap",
]

CLAIM_SUPPORT_STATUSES = [
    "supported",
    "weak",
    "unsupported",
    "contradiction",
    "editorial_rule",
    "not_claim",
]

# media_transcripts (v0.2) — YouTube highlight/presser transcript attachment
MEDIA_TRANSCRIPT_KINDS = ["highlights", "presser"]
MEDIA_TRANSCRIPT_STATUSES = ["ok", "missing"]
TRANSCRIPT_TRACKS = ["auto", "manual"]


def validate_story_angle(angle: dict[str, Any], path: str = "story_angle") -> dict[str, Any]:
    """Validate a single story angle and return it unchanged."""
    errors: list[str] = []
    _validate_story_angle(angle, path, errors)
    return _finish("story angle", angle, errors)


def validate_story_angles(angles: list[dict[str, Any]], path: str = "story_angles") -> list[dict[str, Any]]:
    """Validate the ranked three-angle contract and return it unchanged."""
    errors: list[str] = []
    if not _require_list(angles, path, errors):
        return _finish("story angles", angles, errors)
    if len(angles) != 3:
        errors.append(f"{path} must contain exactly 3 items")
    for index, angle in enumerate(angles):
        _validate_story_angle(angle, f"{path}[{index}]", errors)
    return _finish("story angles", angles, errors)


def validate_normalized_game_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Validate the normalized Mystics postgame packet contract."""
    errors: list[str] = []
    if not _require_mapping(packet, "packet", errors):
        return _finish("normalized game packet", packet, errors)

    _require_keys(
        packet,
        "packet",
        (
            "schema_version",
            "retrieved_at",
            "team",
            "schedule",
            "game",
            "sources",
            "memory",
            "narrative",
            "story_angles",
            "writer_profile",
        ),
        errors,
    )
    _require_exact(packet.get("schema_version"), "mystics-postgame-recap/v0.2", "packet.schema_version", errors)
    _require_str(packet.get("retrieved_at"), "packet.retrieved_at", errors, allow_empty=False)
    _validate_packet_team(packet.get("team"), "packet.team", errors)
    _validate_game(packet.get("game"), "packet.game", errors)
    _validate_sources(packet.get("sources"), "packet.sources", errors)
    _require_mapping(packet.get("memory"), "packet.memory", errors)
    _validate_narrative(packet.get("narrative"), "packet.narrative", errors)
    if "story_angles" in packet:
        _validate_story_angles_exact(packet.get("story_angles"), "packet.story_angles", errors)
    _validate_writer_profile(packet.get("writer_profile"), "packet.writer_profile", errors)
    if "media_transcripts" in packet:
        _validate_media_transcripts(packet.get("media_transcripts"), "packet.media_transcripts", errors)
    return _finish("normalized game packet", packet, errors)


def validate_discord_review_package(package: dict[str, Any]) -> dict[str, Any]:
    """Validate a local Discord-ready review package."""
    errors: list[str] = []
    if not _require_mapping(package, "review_package", errors):
        return _finish("Discord review package", package, errors)

    _require_keys(
        package,
        "review_package",
        (
            "thread_title",
            "summary_message",
            "editor_checklist",
            "article_markdown_path",
            "packet_path",
            "risk_flags",
            "selected_angle",
            "alternate_angles",
            "recommended_status",
        ),
        errors,
    )
    _require_str(package.get("thread_title"), "review_package.thread_title", errors, allow_empty=False)
    _require_str(package.get("summary_message"), "review_package.summary_message", errors, allow_empty=False)
    if isinstance(package.get("summary_message"), str) and "Human review required before publishing." not in package["summary_message"]:
        errors.append("review_package.summary_message must include the human-review-required note")
    _require_list_of_str(package.get("editor_checklist"), "review_package.editor_checklist", errors, allow_empty_items=False)
    _require_str(package.get("article_markdown_path"), "review_package.article_markdown_path", errors, allow_empty=False)
    _require_str(package.get("packet_path"), "review_package.packet_path", errors, allow_empty=False)
    _require_list_of_str(package.get("risk_flags"), "review_package.risk_flags", errors)
    _validate_story_angle(package.get("selected_angle"), "review_package.selected_angle", errors)
    _validate_story_angle_list(package.get("alternate_angles"), "review_package.alternate_angles", errors)
    _require_exact(package.get("recommended_status"), "human_review_required", "review_package.recommended_status", errors)

    if "qa_report_path" in package:
        _require_str(package.get("qa_report_path"), "review_package.qa_report_path", errors, allow_empty=False)
    if "overall_recommendation" in package:
        _require_one_of(package.get("overall_recommendation"), QA_RECOMMENDATIONS, "review_package.overall_recommendation", errors)
    if "lowest_scoring_items" in package:
        _require_list(package.get("lowest_scoring_items"), "review_package.lowest_scoring_items", errors)
    if "top_issue_flags" in package:
        _require_list(package.get("top_issue_flags"), "review_package.top_issue_flags", errors)
    if "external_editor_packet_path" in package:
        _require_str(package.get("external_editor_packet_path"), "review_package.external_editor_packet_path", errors, allow_empty=False)
    if "recommended_external_review" in package:
        _require_bool(package.get("recommended_external_review"), "review_package.recommended_external_review", errors)
    if "external_editor_decision_path" in package:
        _require_str(package.get("external_editor_decision_path"), "review_package.external_editor_decision_path", errors, allow_empty=False)
    if "external_editor_verdict" in package:
        _require_one_of(package.get("external_editor_verdict"), EXTERNAL_EDITOR_VERDICTS, "review_package.external_editor_verdict", errors)
    if "external_editor_confidence" in package:
        _require_number_range(package.get("external_editor_confidence"), "review_package.external_editor_confidence", errors, minimum=0, maximum=1)
    if "external_editor_publish_blockers_count" in package:
        _require_int_range(package.get("external_editor_publish_blockers_count"), "review_package.external_editor_publish_blockers_count", errors, minimum=0)
    if "external_editor_needs_revision" in package:
        _require_bool(package.get("external_editor_needs_revision"), "review_package.external_editor_needs_revision", errors)
    if "human_editor_required" in package:
        _require_bool(package.get("human_editor_required"), "review_package.human_editor_required", errors, must_be=True)
    if "claim_audit_path" in package:
        _require_str(package.get("claim_audit_path"), "review_package.claim_audit_path", errors, allow_empty=False)
    if "claim_audit_summary" in package:
        _validate_claim_review_summary(package.get("claim_audit_summary"), "review_package.claim_audit_summary", errors)
    return _finish("Discord review package", package, errors)


def validate_asset_index(index: dict[str, Any]) -> dict[str, Any]:
    """Validate the generated asset index."""
    errors: list[str] = []
    if not _require_mapping(index, "asset_index", errors):
        return _finish("asset index", index, errors)
    _require_keys(
        index,
        "asset_index",
        (
            "event_id",
            "generation_timestamp",
            "generated_asset_paths",
            "selected_story_angle",
            "writer",
            "risk_summary",
            "review_required",
        ),
        errors,
    )
    _require_str(index.get("event_id"), "asset_index.event_id", errors, allow_empty=False)
    _require_str(index.get("generation_timestamp"), "asset_index.generation_timestamp", errors, allow_empty=False)
    _require_str_dict(index.get("generated_asset_paths"), "asset_index.generated_asset_paths", errors)
    _validate_story_angle(index.get("selected_story_angle"), "asset_index.selected_story_angle", errors)
    _validate_writer(index.get("writer"), "asset_index.writer", errors)
    _validate_risk_summary(index.get("risk_summary"), "asset_index.risk_summary", errors)
    _require_bool(index.get("review_required"), "asset_index.review_required", errors, must_be=True)
    return _finish("asset index", index, errors)


def validate_qa_report(report: dict[str, Any]) -> dict[str, Any]:
    """Validate the advisory editorial QA report."""
    errors: list[str] = []
    if not _require_mapping(report, "qa_report", errors):
        return _finish("QA report", report, errors)
    _require_keys(
        report,
        "qa_report",
        (
            "schema_version",
            "event_id",
            "generation_timestamp",
            "score_categories",
            "supported_issue_flags",
            "selected_story_angle",
            "item_reports",
            "summary",
            "overall_recommendation",
            "advisory_only",
        ),
        errors,
    )
    _require_exact(report.get("schema_version"), "mystics-editorial-qa/v0.1", "qa_report.schema_version", errors)
    _require_str(report.get("event_id"), "qa_report.event_id", errors, allow_empty=False)
    _require_str(report.get("generation_timestamp"), "qa_report.generation_timestamp", errors, allow_empty=False)
    _require_list_of_str(report.get("score_categories"), "qa_report.score_categories", errors)
    if isinstance(report.get("score_categories"), list):
        missing = [category for category in QA_SCORE_CATEGORIES if category not in report["score_categories"]]
        if missing:
            errors.append(f"qa_report.score_categories missing required categories: {', '.join(missing)}")
    _require_list_of_str(report.get("supported_issue_flags"), "qa_report.supported_issue_flags", errors)
    _validate_story_angle(report.get("selected_story_angle"), "qa_report.selected_story_angle", errors)
    _validate_qa_item_reports(report.get("item_reports"), "qa_report.item_reports", errors)
    _validate_qa_summary(report.get("summary"), "qa_report.summary", errors)
    _require_one_of(report.get("overall_recommendation"), QA_RECOMMENDATIONS, "qa_report.overall_recommendation", errors)
    _require_bool(report.get("advisory_only"), "qa_report.advisory_only", errors, must_be=True)
    return _finish("QA report", report, errors)


def validate_claim_evidence_audit(audit: dict[str, Any]) -> dict[str, Any]:
    """Validate the advisory claim evidence audit."""
    errors: list[str] = []
    if not _require_mapping(audit, "claim_audit", errors):
        return _finish("claim evidence audit", audit, errors)
    _require_keys(
        audit,
        "claim_audit",
        (
            "schema_version",
            "event_id",
            "generation_timestamp",
            "claim_categories",
            "support_statuses",
            "article_markdown_path",
            "packet_path",
            "asset_paths",
            "source_inventory",
            "claims",
            "sentence_map",
            "summary",
            "sentence_summary",
            "advisory_only",
            "human_editor_required",
            "no_auto_publish",
        ),
        errors,
    )
    _require_exact(audit.get("schema_version"), "mystics-claim-evidence-audit/v0.2", "claim_audit.schema_version", errors)
    _require_str(audit.get("event_id"), "claim_audit.event_id", errors, allow_empty=False)
    _require_str(audit.get("generation_timestamp"), "claim_audit.generation_timestamp", errors, allow_empty=False)
    _require_list_of_str(audit.get("claim_categories"), "claim_audit.claim_categories", errors)
    if isinstance(audit.get("claim_categories"), list):
        missing = [category for category in CLAIM_AUDIT_CATEGORIES if category not in audit["claim_categories"]]
        if missing:
            errors.append(f"claim_audit.claim_categories missing required categories: {', '.join(missing)}")
    _require_list_of_str(audit.get("support_statuses"), "claim_audit.support_statuses", errors)
    if isinstance(audit.get("support_statuses"), list):
        missing_statuses = [status for status in CLAIM_SUPPORT_STATUSES if status not in audit["support_statuses"]]
        if missing_statuses:
            errors.append(f"claim_audit.support_statuses missing required statuses: {', '.join(missing_statuses)}")
    if audit.get("grounding_method_version") is not None:
        _require_str(audit.get("grounding_method_version"), "claim_audit.grounding_method_version", errors, allow_empty=False)
    if audit.get("article_markdown_path") is not None:
        _require_str(audit.get("article_markdown_path"), "claim_audit.article_markdown_path", errors)
    if audit.get("packet_path") is not None:
        _require_str(audit.get("packet_path"), "claim_audit.packet_path", errors)
    _require_str_dict(audit.get("asset_paths"), "claim_audit.asset_paths", errors)
    _validate_claim_source_inventory(audit.get("source_inventory"), "claim_audit.source_inventory", errors)
    _validate_claim_entries(audit.get("claims"), "claim_audit.claims", errors)
    _validate_sentence_map(audit.get("sentence_map"), "claim_audit.sentence_map", errors)
    _validate_claim_summary(audit.get("summary"), "claim_audit.summary", errors)
    _validate_sentence_summary(audit.get("sentence_summary"), "claim_audit.sentence_summary", errors)
    _validate_claim_audit_consistency(audit, errors)
    _require_bool(audit.get("advisory_only"), "claim_audit.advisory_only", errors, must_be=True)
    _require_bool(audit.get("human_editor_required"), "claim_audit.human_editor_required", errors, must_be=True)
    _require_bool(audit.get("no_auto_publish"), "claim_audit.no_auto_publish", errors, must_be=True)
    return _finish("claim evidence audit", audit, errors)


def validate_external_editor_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Validate a local packet prepared for external editor review."""
    errors: list[str] = []
    if not _require_mapping(packet, "external_editor_packet", errors):
        return _finish("external editor packet", packet, errors)
    _require_keys(
        packet,
        "external_editor_packet",
        (
            "schema_version",
            "editor_prompt",
            "main_article_markdown",
            "generated_assets",
            "normalized_game_packet_summary",
            "story_angles",
            "memory_context_summary",
            "internal_qa_summary",
            "editorial_rules",
            "source_event_id",
            "generated_timestamp",
            "source_paths",
            "external_review_only",
            "no_auto_publish",
            "no_auto_rewrite",
        ),
        errors,
    )
    _require_exact(packet.get("schema_version"), "mystics-external-editor-review/v0.1", "external_editor_packet.schema_version", errors)
    _require_str(packet.get("editor_prompt"), "external_editor_packet.editor_prompt", errors, allow_empty=False)
    _require_str(packet.get("main_article_markdown"), "external_editor_packet.main_article_markdown", errors, allow_empty=False)
    _require_mapping(packet.get("generated_assets"), "external_editor_packet.generated_assets", errors)
    _require_mapping(packet.get("normalized_game_packet_summary"), "external_editor_packet.normalized_game_packet_summary", errors)
    _validate_story_angles_exact(packet.get("story_angles"), "external_editor_packet.story_angles", errors)
    _require_mapping(packet.get("memory_context_summary"), "external_editor_packet.memory_context_summary", errors)
    _validate_external_qa_summary(packet.get("internal_qa_summary"), "external_editor_packet.internal_qa_summary", errors)
    _require_list_of_str(packet.get("editorial_rules"), "external_editor_packet.editorial_rules", errors)
    _require_str(packet.get("source_event_id"), "external_editor_packet.source_event_id", errors, allow_empty=False)
    _require_str(packet.get("generated_timestamp"), "external_editor_packet.generated_timestamp", errors, allow_empty=False)
    _require_mapping(packet.get("source_paths"), "external_editor_packet.source_paths", errors)
    _require_bool(packet.get("external_review_only"), "external_editor_packet.external_review_only", errors, must_be=True)
    _require_bool(packet.get("no_auto_publish"), "external_editor_packet.no_auto_publish", errors, must_be=True)
    _require_bool(packet.get("no_auto_rewrite"), "external_editor_packet.no_auto_rewrite", errors, must_be=True)
    return _finish("external editor packet", packet, errors)


def validate_external_editor_response(response: dict[str, Any]) -> dict[str, Any]:
    """Validate a raw external editor response and return it unchanged."""
    errors: list[str] = []
    if not _require_mapping(response, "external_editor_response", errors):
        return _finish("external editor response", response, errors)
    _require_keys(response, "external_editor_response", tuple(EXTERNAL_EDITOR_RESPONSE_FIELDS), errors)
    _require_one_of(response.get("overall_verdict"), EXTERNAL_EDITOR_VERDICTS, "external_editor_response.overall_verdict", errors)
    _require_list(response.get("article_notes"), "external_editor_response.article_notes", errors)
    _require_mapping(response.get("asset_notes"), "external_editor_response.asset_notes", errors)
    for field in ("factual_risks", "unsupported_claims", "headline_feedback", "voice_feedback", "recommended_edits", "publish_blockers"):
        _require_list(response.get(field), f"external_editor_response.{field}", errors)
    _require_str(response.get("suggested_headline"), "external_editor_response.suggested_headline", errors)
    _require_number_range(response.get("confidence"), "external_editor_response.confidence", errors, minimum=0, maximum=1)
    return _finish("external editor response", response, errors)


def validate_normalized_external_editor_response(envelope: dict[str, Any]) -> dict[str, Any]:
    """Validate the stored external editor response envelope."""
    errors: list[str] = []
    if not _require_mapping(envelope, "external_editor_response_envelope", errors):
        return _finish("normalized external editor response", envelope, errors)
    _require_keys(
        envelope,
        "external_editor_response_envelope",
        (
            "schema_version",
            "event_id",
            "source_response_path",
            "generated_timestamp",
            "response",
            "advisory_only",
            "human_editor_required",
            "no_auto_publish",
            "no_auto_rewrite",
        ),
        errors,
    )
    _require_exact(
        envelope.get("schema_version"),
        "mystics-external-editor-response/v0.1",
        "external_editor_response_envelope.schema_version",
        errors,
    )
    _require_str(envelope.get("event_id"), "external_editor_response_envelope.event_id", errors, allow_empty=False)
    _require_str(envelope.get("source_response_path"), "external_editor_response_envelope.source_response_path", errors, allow_empty=False)
    _require_str(envelope.get("generated_timestamp"), "external_editor_response_envelope.generated_timestamp", errors, allow_empty=False)
    if "response" in envelope:
        response_errors: list[str] = []
        _validate_external_editor_response(envelope.get("response"), "external_editor_response_envelope.response", response_errors)
        errors.extend(response_errors)
    _require_bool(envelope.get("advisory_only"), "external_editor_response_envelope.advisory_only", errors, must_be=True)
    _require_bool(envelope.get("human_editor_required"), "external_editor_response_envelope.human_editor_required", errors, must_be=True)
    _require_bool(envelope.get("no_auto_publish"), "external_editor_response_envelope.no_auto_publish", errors, must_be=True)
    _require_bool(envelope.get("no_auto_rewrite"), "external_editor_response_envelope.no_auto_rewrite", errors, must_be=True)
    return _finish("normalized external editor response", envelope, errors)


def validate_external_editor_decision_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Validate the external editor decision summary."""
    errors: list[str] = []
    if not _require_mapping(summary, "external_editor_decision", errors):
        return _finish("external editor decision summary", summary, errors)
    _require_keys(
        summary,
        "external_editor_decision",
        (
            "schema_version",
            "event_id",
            "source_response_path",
            "normalized_response_path",
            "overall_verdict",
            "confidence",
            "publish_blockers_count",
            "unsupported_claims_count",
            "recommended_edits_count",
            "needs_revision",
            "safe_to_publish_candidate",
            "human_editor_required",
            "generated_timestamp",
            "advisory_only",
            "no_auto_publish",
            "no_auto_rewrite",
        ),
        errors,
    )
    _require_exact(summary.get("schema_version"), "mystics-external-editor-decision/v0.1", "external_editor_decision.schema_version", errors)
    _require_str(summary.get("event_id"), "external_editor_decision.event_id", errors, allow_empty=False)
    _require_str(summary.get("source_response_path"), "external_editor_decision.source_response_path", errors, allow_empty=False)
    _require_str(summary.get("normalized_response_path"), "external_editor_decision.normalized_response_path", errors, allow_empty=False)
    _require_one_of(summary.get("overall_verdict"), EXTERNAL_EDITOR_VERDICTS, "external_editor_decision.overall_verdict", errors)
    _require_number_range(summary.get("confidence"), "external_editor_decision.confidence", errors, minimum=0, maximum=1)
    for field in ("publish_blockers_count", "unsupported_claims_count", "recommended_edits_count"):
        _require_int_range(summary.get(field), f"external_editor_decision.{field}", errors, minimum=0)
    _require_bool(summary.get("needs_revision"), "external_editor_decision.needs_revision", errors)
    _require_bool(summary.get("safe_to_publish_candidate"), "external_editor_decision.safe_to_publish_candidate", errors)
    _require_bool(summary.get("human_editor_required"), "external_editor_decision.human_editor_required", errors, must_be=True)
    _require_str(summary.get("generated_timestamp"), "external_editor_decision.generated_timestamp", errors, allow_empty=False)
    _require_bool(summary.get("advisory_only"), "external_editor_decision.advisory_only", errors, must_be=True)
    _require_bool(summary.get("no_auto_publish"), "external_editor_decision.no_auto_publish", errors, must_be=True)
    _require_bool(summary.get("no_auto_rewrite"), "external_editor_decision.no_auto_rewrite", errors, must_be=True)
    return _finish("external editor decision summary", summary, errors)


def _validate_story_angles_exact(value: Any, path: str, errors: list[str]) -> None:
    if not _require_list(value, path, errors):
        return
    if len(value) != 3:
        errors.append(f"{path} must contain exactly 3 items")
    for index, angle in enumerate(value):
        _validate_story_angle(angle, f"{path}[{index}]", errors)


def _validate_story_angle_list(value: Any, path: str, errors: list[str]) -> None:
    if not _require_list(value, path, errors):
        return
    for index, angle in enumerate(value):
        _validate_story_angle(angle, f"{path}[{index}]", errors)


def _validate_story_angle(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(value, path, ("angle_title", "angle_summary", "confidence", "supporting_signals", "risk_flags"), errors)
    _require_str(value.get("angle_title"), f"{path}.angle_title", errors, allow_empty=False)
    _require_str(value.get("angle_summary"), f"{path}.angle_summary", errors, allow_empty=False)
    _require_number_range(value.get("confidence"), f"{path}.confidence", errors, minimum=0, maximum=1)
    _require_list_of_str(value.get("supporting_signals"), f"{path}.supporting_signals", errors)
    _require_list_of_str(value.get("risk_flags"), f"{path}.risk_flags", errors)


def _validate_packet_team(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(value, path, ("id", "name", "abbreviation", "league"), errors)
    for field in ("id", "name", "abbreviation", "league"):
        _require_str(value.get(field), f"{path}.{field}", errors, allow_empty=False)


def _validate_game(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(
        value,
        path,
        ("id", "date", "status", "teams", "scoring_by_quarter", "leaders", "play_by_play", "gamecast"),
        errors,
    )
    _require_str(value.get("id"), f"{path}.id", errors, allow_empty=False)
    _require_str(value.get("date"), f"{path}.date", errors, allow_empty=False)
    _validate_status(value.get("status"), f"{path}.status", errors)
    _validate_game_teams(value.get("teams"), f"{path}.teams", errors)
    _validate_scoring_by_quarter(value.get("scoring_by_quarter"), f"{path}.scoring_by_quarter", errors)
    _require_mapping(value.get("leaders"), f"{path}.leaders", errors)
    _validate_play_by_play(value.get("play_by_play"), f"{path}.play_by_play", errors)
    _validate_gamecast(value.get("gamecast"), f"{path}.gamecast", errors)


def _validate_status(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(value, path, ("name", "description", "completed"), errors)
    _require_str(value.get("name"), f"{path}.name", errors)
    _require_str(value.get("description"), f"{path}.description", errors)
    _require_bool(value.get("completed"), f"{path}.completed", errors)


def _validate_game_teams(value: Any, path: str, errors: list[str]) -> None:
    if not _require_list(value, path, errors):
        return
    if len(value) < 2:
        errors.append(f"{path} must include at least 2 teams")
    for index, team in enumerate(value):
        team_path = f"{path}[{index}]"
        if not _require_mapping(team, team_path, errors):
            continue
        _require_keys(team, team_path, ("id", "name", "abbreviation", "home_away", "score", "winner", "line_score", "team_stats", "box_score"), errors)
        for field in ("id", "name", "abbreviation", "home_away"):
            _require_str(team.get(field), f"{team_path}.{field}", errors, allow_empty=False)
        _require_int_range(team.get("score"), f"{team_path}.score", errors, minimum=0)
        _require_bool(team.get("winner"), f"{team_path}.winner", errors)
        _require_list(team.get("line_score"), f"{team_path}.line_score", errors)
        _require_mapping(team.get("team_stats"), f"{team_path}.team_stats", errors)
        _require_list(team.get("box_score"), f"{team_path}.box_score", errors)


def _validate_scoring_by_quarter(value: Any, path: str, errors: list[str]) -> None:
    if not _require_list(value, path, errors):
        return
    for index, row in enumerate(value):
        row_path = f"{path}[{index}]"
        if not _require_mapping(row, row_path, errors):
            continue
        _require_int_range(row.get("period"), f"{row_path}.period", errors, minimum=1)
        _require_str(row.get("label"), f"{row_path}.label", errors)


def _validate_play_by_play(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(value, path, ("available", "play_count", "scoring_play_count", "scoring_plays", "notable_plays"), errors)
    _require_bool(value.get("available"), f"{path}.available", errors)
    _require_int_range(value.get("play_count"), f"{path}.play_count", errors, minimum=0)
    _require_int_range(value.get("scoring_play_count"), f"{path}.scoring_play_count", errors, minimum=0)
    _require_list(value.get("scoring_plays"), f"{path}.scoring_plays", errors)
    _require_list(value.get("notable_plays"), f"{path}.notable_plays", errors)


def _validate_gamecast(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(value, path, ("available", "win_probability_available", "win_probability_samples", "article_available", "video_count"), errors)
    for field in ("available", "win_probability_available", "article_available"):
        _require_bool(value.get(field), f"{path}.{field}", errors)
    for field in ("win_probability_samples", "video_count"):
        _require_int_range(value.get(field), f"{path}.{field}", errors, minimum=0)


def _validate_sources(value: Any, path: str, errors: list[str]) -> None:
    if not _require_list(value, path, errors):
        return
    if not value:
        errors.append(f"{path} must include at least 1 source")
    for index, source in enumerate(value):
        source_path = f"{path}[{index}]"
        if not _require_mapping(source, source_path, errors):
            continue
        _require_keys(source, source_path, ("name", "url", "retrieved_at"), errors)
        _require_str(source.get("name"), f"{source_path}.name", errors, allow_empty=False)
        _require_str(source.get("url"), f"{source_path}.url", errors)
        _require_str(source.get("retrieved_at"), f"{source_path}.retrieved_at", errors, allow_empty=False)


def _validate_media_transcripts(value: Any, path: str, errors: list[str]) -> None:
    """Validate the optional v0.2 media_transcripts block (list of per-video objects).

    Both successful (status "ok") and failed (status "missing") records are
    accepted; a missing record only needs a reason. Raw segments/text and the
    name-corrected variant are both required for ok records.
    """
    if not _require_list(value, path, errors):
        return
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not _require_mapping(item, item_path, errors):
            continue
        _require_keys(item, item_path, ("video_id", "kind", "status", "source_url", "retrieved_at"), errors)
        _require_str(item.get("video_id"), f"{item_path}.video_id", errors, allow_empty=False)
        _require_one_of(item.get("kind"), MEDIA_TRANSCRIPT_KINDS, f"{item_path}.kind", errors)
        _require_one_of(item.get("status"), MEDIA_TRANSCRIPT_STATUSES, f"{item_path}.status", errors)
        _require_str(item.get("source_url"), f"{item_path}.source_url", errors, allow_empty=False)
        _require_str(item.get("retrieved_at"), f"{item_path}.retrieved_at", errors, allow_empty=False)
        status = item.get("status")
        if status == "ok":
            _require_one_of(item.get("track"), TRANSCRIPT_TRACKS, f"{item_path}.track", errors)
            _require_str(item.get("language"), f"{item_path}.language", errors, allow_empty=False)
            _require_int_range(item.get("snippet_count"), f"{item_path}.snippet_count", errors, minimum=0)
            _require_int_range(item.get("char_count"), f"{item_path}.char_count", errors, minimum=0)
            _validate_transcript_segments(item.get("segments"), f"{item_path}.segments", errors)
            _validate_transcript_segments(item.get("corrected_segments"), f"{item_path}.corrected_segments", errors)
            _require_str(item.get("text"), f"{item_path}.text", errors)
            _require_str(item.get("corrected_text"), f"{item_path}.corrected_text", errors)
            _validate_name_corrections(item.get("name_corrections"), f"{item_path}.name_corrections", errors)
        elif status == "missing":
            _require_str(item.get("reason"), f"{item_path}.reason", errors, allow_empty=False)


def _validate_transcript_segments(value: Any, path: str, errors: list[str]) -> None:
    if not _require_list(value, path, errors):
        return
    for index, segment in enumerate(value):
        segment_path = f"{path}[{index}]"
        if not _require_mapping(segment, segment_path, errors):
            continue
        _require_keys(segment, segment_path, ("start", "duration", "text"), errors)
        _require_number_range(segment.get("start"), f"{segment_path}.start", errors, minimum=0)
        _require_number_range(segment.get("duration"), f"{segment_path}.duration", errors, minimum=0)
        _require_str(segment.get("text"), f"{segment_path}.text", errors)


def _validate_name_corrections(value: Any, path: str, errors: list[str]) -> None:
    if not _require_list(value, path, errors):
        return
    for index, correction in enumerate(value):
        correction_path = f"{path}[{index}]"
        if not _require_mapping(correction, correction_path, errors):
            continue
        _require_keys(correction, correction_path, ("from", "to", "count"), errors)
        _require_str(correction.get("from"), f"{correction_path}.from", errors, allow_empty=False)
        _require_str(correction.get("to"), f"{correction_path}.to", errors, allow_empty=False)
        _require_int_range(correction.get("count"), f"{correction_path}.count", errors, minimum=1)


def _validate_narrative(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(
        value,
        path,
        (
            "final_score",
            "result",
            "top_performers",
            "biggest_scoring_run",
            "key_quarter_or_turning_point",
            "stat_edges",
            "likely_article_angles",
        ),
        errors,
    )
    _require_str(value.get("final_score"), f"{path}.final_score", errors, allow_empty=False)
    _require_one_of(value.get("result"), ("win", "loss"), f"{path}.result", errors)
    _require_list(value.get("top_performers"), f"{path}.top_performers", errors)
    _require_mapping(value.get("biggest_scoring_run"), f"{path}.biggest_scoring_run", errors)
    _require_mapping(value.get("key_quarter_or_turning_point"), f"{path}.key_quarter_or_turning_point", errors)
    _require_mapping(value.get("stat_edges"), f"{path}.stat_edges", errors)
    _require_list_of_str(value.get("likely_article_angles"), f"{path}.likely_article_angles", errors)


def _validate_writer_profile(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(value, path, ("name", "title", "voice", "guardrails"), errors)
    for field in ("name", "title", "voice"):
        _require_str(value.get(field), f"{path}.{field}", errors, allow_empty=False)
    _require_list_of_str(value.get("guardrails"), f"{path}.guardrails", errors)


def _validate_writer(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(value, path, ("name", "voice"), errors)
    _require_str(value.get("name"), f"{path}.name", errors, allow_empty=False)
    _require_str(value.get("voice"), f"{path}.voice", errors, allow_empty=False)


def _validate_risk_summary(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(value, path, ("summary", "flags", "editorial_rules"), errors)
    _require_str(value.get("summary"), f"{path}.summary", errors, allow_empty=False)
    _require_list_of_str(value.get("flags"), f"{path}.flags", errors)
    _require_list_of_str(value.get("editorial_rules"), f"{path}.editorial_rules", errors)


def _validate_qa_item_reports(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    if not value:
        errors.append(f"{path} must include at least 1 item report")
    for key, report in value.items():
        report_path = f"{path}.{key}"
        if not _require_mapping(report, report_path, errors):
            continue
        _require_keys(report, report_path, ("item_key", "label", "word_count", "character_count", "issue_flags", "scores", "overall_score", "notes"), errors)
        _require_str(report.get("item_key"), f"{report_path}.item_key", errors, allow_empty=False)
        _require_str(report.get("label"), f"{report_path}.label", errors, allow_empty=False)
        if report.get("path") is not None:
            _require_str(report.get("path"), f"{report_path}.path", errors)
        _require_int_range(report.get("word_count"), f"{report_path}.word_count", errors, minimum=0)
        _require_int_range(report.get("character_count"), f"{report_path}.character_count", errors, minimum=0)
        _require_list_of_str(report.get("issue_flags"), f"{report_path}.issue_flags", errors)
        _validate_qa_scores(report.get("scores"), f"{report_path}.scores", errors)
        _require_int_range(report.get("overall_score"), f"{report_path}.overall_score", errors, minimum=0, maximum=100)
        _require_list_of_str(report.get("notes"), f"{report_path}.notes", errors)


def _validate_qa_scores(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    for category in QA_SCORE_CATEGORIES:
        if category not in value:
            errors.append(f"{path} missing required key: {category}")
            continue
        _require_int_range(value.get(category), f"{path}.{category}", errors, minimum=0, maximum=100)


def _validate_qa_summary(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(value, path, ("overall_recommendation", "lowest_scoring_items", "top_issue_flags", "item_count"), errors)
    _require_one_of(value.get("overall_recommendation"), QA_RECOMMENDATIONS, f"{path}.overall_recommendation", errors)
    _require_list(value.get("lowest_scoring_items"), f"{path}.lowest_scoring_items", errors)
    _require_list(value.get("top_issue_flags"), f"{path}.top_issue_flags", errors)
    _require_int_range(value.get("item_count"), f"{path}.item_count", errors, minimum=1)


def _validate_external_qa_summary(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(value, path, ("available",), errors)
    _require_bool(value.get("available"), f"{path}.available", errors)
    if value.get("available"):
        if "overall_recommendation" in value:
            _require_one_of(value.get("overall_recommendation"), QA_RECOMMENDATIONS, f"{path}.overall_recommendation", errors)
        if "summary" in value:
            _require_mapping(value.get("summary"), f"{path}.summary", errors)
        if "item_reports" in value:
            _require_mapping(value.get("item_reports"), f"{path}.item_reports", errors)


def _validate_claim_source_inventory(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(value, path, ("source_count", "source_families", "second_source_present", "sources"), errors)
    _require_int_range(value.get("source_count"), f"{path}.source_count", errors, minimum=0)
    _require_list_of_str(value.get("source_families"), f"{path}.source_families", errors)
    _require_bool(value.get("second_source_present"), f"{path}.second_source_present", errors)
    if _require_list(value.get("sources"), f"{path}.sources", errors):
        for index, source in enumerate(value.get("sources") or []):
            source_path = f"{path}.sources[{index}]"
            if not _require_mapping(source, source_path, errors):
                continue
            _require_keys(source, source_path, ("name", "url"), errors)
            _require_str(source.get("name"), f"{source_path}.name", errors, allow_empty=False)
            _require_str(source.get("url"), f"{source_path}.url", errors)


def _validate_claim_entries(value: Any, path: str, errors: list[str]) -> None:
    if not _require_list(value, path, errors):
        return
    for index, claim in enumerate(value):
        claim_path = f"{path}[{index}]"
        if not _require_mapping(claim, claim_path, errors):
            continue
        _require_keys(claim, claim_path, ("item_key", "claim", "category", "evidence_paths", "notes"), errors)
        _require_str(claim.get("item_key"), f"{claim_path}.item_key", errors, allow_empty=False)
        _require_str(claim.get("claim"), f"{claim_path}.claim", errors, allow_empty=False)
        _require_one_of(claim.get("category"), CLAIM_AUDIT_CATEGORIES, f"{claim_path}.category", errors)
        _require_list_of_str(claim.get("evidence_paths"), f"{claim_path}.evidence_paths", errors)
        _require_list_of_str(claim.get("notes"), f"{claim_path}.notes", errors)


def _validate_sentence_map(value: Any, path: str, errors: list[str]) -> None:
    if not _require_list(value, path, errors):
        return
    seen_ids = set()
    for index, sentence in enumerate(value):
        sentence_path = f"{path}[{index}]"
        if not _require_mapping(sentence, sentence_path, errors):
            continue
        _require_keys(
            sentence,
            sentence_path,
            (
                "sentence_id",
                "item_key",
                "section",
                "text",
                "claim_types",
                "support_status",
                "support_confidence",
                "evidence_refs",
                "risk_flags",
                "notes",
            ),
            errors,
        )
        sentence_id = sentence.get("sentence_id")
        _require_str(sentence_id, f"{sentence_path}.sentence_id", errors, allow_empty=False)
        if isinstance(sentence_id, str):
            if sentence_id in seen_ids:
                errors.append(f"{sentence_path}.sentence_id must be unique")
            seen_ids.add(sentence_id)
        _require_str(sentence.get("item_key"), f"{sentence_path}.item_key", errors, allow_empty=False)
        _require_str(sentence.get("section"), f"{sentence_path}.section", errors, allow_empty=False)
        _require_str(sentence.get("text"), f"{sentence_path}.text", errors, allow_empty=False)
        _require_list_of_str(sentence.get("claim_types"), f"{sentence_path}.claim_types", errors)
        _require_one_of(sentence.get("support_status"), CLAIM_SUPPORT_STATUSES, f"{sentence_path}.support_status", errors)
        _require_number_range(sentence.get("support_confidence"), f"{sentence_path}.support_confidence", errors, minimum=0, maximum=1)
        _validate_evidence_refs(sentence.get("evidence_refs"), f"{sentence_path}.evidence_refs", errors)
        _require_list_of_str(sentence.get("risk_flags"), f"{sentence_path}.risk_flags", errors)
        _require_list_of_str(sentence.get("notes"), f"{sentence_path}.notes", errors)


def _validate_evidence_refs(value: Any, path: str, errors: list[str]) -> None:
    if not _require_list(value, path, errors):
        return
    for index, ref in enumerate(value):
        ref_path = f"{path}[{index}]"
        if not _require_mapping(ref, ref_path, errors):
            continue
        _require_keys(ref, ref_path, ("path", "value", "source_family"), errors)
        _require_str(ref.get("path"), f"{ref_path}.path", errors, allow_empty=False)
        _require_str(ref.get("value"), f"{ref_path}.value", errors)
        _require_str(ref.get("source_family"), f"{ref_path}.source_family", errors, allow_empty=False)


def _validate_claim_summary(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(
        value,
        path,
        (
            "total_claims",
            "category_counts",
            "source_count",
            "second_source_present",
            "washington_mentions",
            "opponent_mentions",
            "top_mystics_performer",
            "top_mystics_performer_surfaced",
            "warning_count",
        ),
        errors,
    )
    _require_int_range(value.get("total_claims"), f"{path}.total_claims", errors, minimum=0)
    _validate_claim_category_counts(value.get("category_counts"), f"{path}.category_counts", errors)
    _require_int_range(value.get("source_count"), f"{path}.source_count", errors, minimum=0)
    _require_bool(value.get("second_source_present"), f"{path}.second_source_present", errors)
    _require_int_range(value.get("washington_mentions"), f"{path}.washington_mentions", errors, minimum=0)
    _require_int_range(value.get("opponent_mentions"), f"{path}.opponent_mentions", errors, minimum=0)
    _require_str(value.get("top_mystics_performer"), f"{path}.top_mystics_performer", errors)
    _require_bool(value.get("top_mystics_performer_surfaced"), f"{path}.top_mystics_performer_surfaced", errors)
    _require_int_range(value.get("warning_count"), f"{path}.warning_count", errors, minimum=0)


def _validate_sentence_summary(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(
        value,
        path,
        (
            "total_sentences",
            "claim_sentence_count",
            "status_counts",
            "unsupported_sentence_count",
            "weak_sentence_count",
            "contradiction_count",
            "editorial_rule_sentence_count",
            "lowest_confidence_sentence_ids",
        ),
        errors,
    )
    _require_int_range(value.get("total_sentences"), f"{path}.total_sentences", errors, minimum=0)
    _require_int_range(value.get("claim_sentence_count"), f"{path}.claim_sentence_count", errors, minimum=0)
    _validate_sentence_status_counts(value.get("status_counts"), f"{path}.status_counts", errors)
    _require_int_range(value.get("unsupported_sentence_count"), f"{path}.unsupported_sentence_count", errors, minimum=0)
    _require_int_range(value.get("weak_sentence_count"), f"{path}.weak_sentence_count", errors, minimum=0)
    _require_int_range(value.get("contradiction_count"), f"{path}.contradiction_count", errors, minimum=0)
    _require_int_range(value.get("editorial_rule_sentence_count"), f"{path}.editorial_rule_sentence_count", errors, minimum=0)
    _require_list_of_str(value.get("lowest_confidence_sentence_ids"), f"{path}.lowest_confidence_sentence_ids", errors)


def _validate_sentence_status_counts(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    for status in CLAIM_SUPPORT_STATUSES:
        if status not in value:
            errors.append(f"{path} missing required key: {status}")
            continue
        _require_int_range(value.get(status), f"{path}.{status}", errors, minimum=0)


def _validate_claim_review_summary(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(value, path, ("total_claims", "category_counts", "warning_count", "second_source_present"), errors)
    _require_int_range(value.get("total_claims"), f"{path}.total_claims", errors, minimum=0)
    _validate_claim_category_counts(value.get("category_counts"), f"{path}.category_counts", errors)
    _require_int_range(value.get("warning_count"), f"{path}.warning_count", errors, minimum=0)
    _require_bool(value.get("second_source_present"), f"{path}.second_source_present", errors)
    if "unsupported_sentence_count" in value:
        _require_int_range(value.get("unsupported_sentence_count"), f"{path}.unsupported_sentence_count", errors, minimum=0)
    if "weak_sentence_count" in value:
        _require_int_range(value.get("weak_sentence_count"), f"{path}.weak_sentence_count", errors, minimum=0)
    if "contradiction_count" in value:
        _require_int_range(value.get("contradiction_count"), f"{path}.contradiction_count", errors, minimum=0)
    if "lowest_confidence_sentence_ids" in value:
        _require_list_of_str(value.get("lowest_confidence_sentence_ids"), f"{path}.lowest_confidence_sentence_ids", errors)


def _validate_claim_category_counts(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    for category in CLAIM_AUDIT_CATEGORIES:
        if category not in value:
            errors.append(f"{path} missing required key: {category}")
            continue
        _require_int_range(value.get(category), f"{path}.{category}", errors, minimum=0)


def _validate_claim_audit_consistency(audit: dict[str, Any], errors: list[str]) -> None:
    source_inventory = audit.get("source_inventory")
    if isinstance(source_inventory, dict):
        source_count = source_inventory.get("source_count")
        sources = source_inventory.get("sources")
        if _is_int(source_count) and isinstance(sources, list) and source_count != len(sources):
            errors.append(
                "claim_audit.source_inventory.source_count must equal "
                f"len(claim_audit.source_inventory.sources) ({len(sources)})"
            )

    _validate_sentence_audit_consistency(audit, errors)

    claims = audit.get("claims")
    summary = audit.get("summary")
    if not isinstance(claims, list) or not isinstance(summary, dict):
        return

    total_claims = summary.get("total_claims")
    if _is_int(total_claims) and total_claims != len(claims):
        errors.append(f"claim_audit.summary.total_claims must equal len(claim_audit.claims) ({len(claims)})")

    category_counts = summary.get("category_counts")
    if not isinstance(category_counts, dict):
        return

    if not all(_is_int(category_counts.get(category)) for category in CLAIM_AUDIT_CATEGORIES):
        return

    category_total = sum(category_counts[category] for category in CLAIM_AUDIT_CATEGORIES)
    if _is_int(total_claims) and category_total != total_claims:
        errors.append(f"claim_audit.summary.category_counts must sum to total_claims ({total_claims})")

    actual_counts = {category: 0 for category in CLAIM_AUDIT_CATEGORIES}
    for claim in claims:
        if not isinstance(claim, dict):
            return
        category = claim.get("category")
        if category not in actual_counts:
            return
        actual_counts[category] += 1

    for category, actual_count in actual_counts.items():
        if category_counts[category] != actual_count:
            errors.append(f"claim_audit.summary.category_counts.{category} must equal actual claim count {actual_count}")

    warning_count = summary.get("warning_count")
    actual_warning_count = sum(actual_counts[category] for category in CLAIM_AUDIT_WARNING_CATEGORIES)
    if _is_int(warning_count) and warning_count != actual_warning_count:
        errors.append(f"claim_audit.summary.warning_count must equal actual warning claim count {actual_warning_count}")


def _validate_sentence_audit_consistency(audit: dict[str, Any], errors: list[str]) -> None:
    sentence_map = audit.get("sentence_map")
    sentence_summary = audit.get("sentence_summary")
    if not isinstance(sentence_map, list) or not isinstance(sentence_summary, dict):
        return

    total_sentences = sentence_summary.get("total_sentences")
    if _is_int(total_sentences) and total_sentences != len(sentence_map):
        errors.append(
            "claim_audit.sentence_summary.total_sentences must equal "
            f"len(claim_audit.sentence_map) ({len(sentence_map)})"
        )

    actual_counts = {status: 0 for status in CLAIM_SUPPORT_STATUSES}
    sentence_ids = set()
    for sentence in sentence_map:
        if not isinstance(sentence, dict):
            return
        sentence_id = sentence.get("sentence_id")
        if isinstance(sentence_id, str):
            sentence_ids.add(sentence_id)
        status = sentence.get("support_status")
        if status not in actual_counts:
            return
        actual_counts[status] += 1

    status_counts = sentence_summary.get("status_counts")
    if not isinstance(status_counts, dict):
        return
    if not all(_is_int(status_counts.get(status)) for status in CLAIM_SUPPORT_STATUSES):
        return

    for status, actual_count in actual_counts.items():
        if status_counts[status] != actual_count:
            errors.append(f"claim_audit.sentence_summary.status_counts.{status} must equal actual sentence count {actual_count}")

    claim_sentence_count = sentence_summary.get("claim_sentence_count")
    actual_claim_sentence_count = len(sentence_map) - actual_counts["not_claim"]
    if _is_int(claim_sentence_count) and claim_sentence_count != actual_claim_sentence_count:
        errors.append(
            "claim_audit.sentence_summary.claim_sentence_count must equal "
            f"non-not_claim sentence count {actual_claim_sentence_count}"
        )

    count_fields = {
        "unsupported_sentence_count": "unsupported",
        "weak_sentence_count": "weak",
        "contradiction_count": "contradiction",
        "editorial_rule_sentence_count": "editorial_rule",
    }
    for field, status in count_fields.items():
        value = sentence_summary.get(field)
        if _is_int(value) and value != actual_counts[status]:
            errors.append(f"claim_audit.sentence_summary.{field} must equal actual {status} sentence count {actual_counts[status]}")

    lowest_ids = sentence_summary.get("lowest_confidence_sentence_ids")
    if isinstance(lowest_ids, list):
        for sentence_id in lowest_ids:
            if isinstance(sentence_id, str) and sentence_id not in sentence_ids:
                errors.append(
                    "claim_audit.sentence_summary.lowest_confidence_sentence_ids "
                    f"contains unknown sentence_id: {sentence_id}"
                )


def _validate_external_editor_response(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    _require_keys(value, path, tuple(EXTERNAL_EDITOR_RESPONSE_FIELDS), errors)
    _require_one_of(value.get("overall_verdict"), EXTERNAL_EDITOR_VERDICTS, f"{path}.overall_verdict", errors)
    _require_list(value.get("article_notes"), f"{path}.article_notes", errors)
    _require_mapping(value.get("asset_notes"), f"{path}.asset_notes", errors)
    for field in ("factual_risks", "unsupported_claims", "headline_feedback", "voice_feedback", "recommended_edits", "publish_blockers"):
        _require_list(value.get(field), f"{path}.{field}", errors)
    _require_str(value.get("suggested_headline"), f"{path}.suggested_headline", errors)
    _require_number_range(value.get("confidence"), f"{path}.confidence", errors, minimum=0, maximum=1)


def _require_keys(value: dict[str, Any], path: str, keys: tuple[str, ...], errors: list[str]) -> None:
    for key in keys:
        if key not in value:
            errors.append(f"{path} missing required key: {key}")


def _require_mapping(value: Any, path: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return False
    return True


def _require_list(value: Any, path: str, errors: list[str]) -> bool:
    if not isinstance(value, list):
        errors.append(f"{path} must be a list")
        return False
    return True


def _require_str(value: Any, path: str, errors: list[str], *, allow_empty: bool = True) -> None:
    if not isinstance(value, str):
        errors.append(f"{path} must be a string")
        return
    if not allow_empty and not value.strip():
        errors.append(f"{path} must not be empty")


def _require_bool(value: Any, path: str, errors: list[str], *, must_be: bool | None = None) -> None:
    if not isinstance(value, bool):
        errors.append(f"{path} must be a boolean")
        return
    if must_be is not None and value is not must_be:
        errors.append(f"{path} must be {must_be}")


def _require_int_range(
    value: Any,
    path: str,
    errors: list[str],
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        errors.append(f"{path} must be an integer")
        return
    if minimum is not None and value < minimum:
        errors.append(f"{path} must be >= {minimum}")
    if maximum is not None and value > maximum:
        errors.append(f"{path} must be <= {maximum}")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_number_range(
    value: Any,
    path: str,
    errors: list[str],
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{path} must be a number")
        return
    numeric = float(value)
    if minimum is not None and numeric < minimum:
        errors.append(f"{path} must be >= {minimum}")
    if maximum is not None and numeric > maximum:
        errors.append(f"{path} must be <= {maximum}")


def _require_one_of(value: Any, choices: tuple[str, ...] | list[str], path: str, errors: list[str]) -> None:
    if value not in choices:
        errors.append(f"{path} must be one of: {', '.join(choices)}")


def _require_exact(value: Any, expected: Any, path: str, errors: list[str]) -> None:
    if value != expected:
        errors.append(f"{path} must be {expected!r}")


def _require_list_of_str(value: Any, path: str, errors: list[str], *, allow_empty_items: bool = True) -> None:
    if not _require_list(value, path, errors):
        return
    for index, item in enumerate(value):
        _require_str(item, f"{path}[{index}]", errors, allow_empty=allow_empty_items)


def _require_str_dict(value: Any, path: str, errors: list[str]) -> None:
    if not _require_mapping(value, path, errors):
        return
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            errors.append(f"{path} keys must be non-empty strings")
        _require_str(item, f"{path}.{key}", errors, allow_empty=False)


def _finish(label: str, value: Any, errors: list[str]) -> Any:
    if errors:
        raise ValueError(f"Invalid {label}: {'; '.join(errors)}")
    return value
