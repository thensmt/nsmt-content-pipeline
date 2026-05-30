"""Deterministic claim evidence audit for Mystics recap artifacts.

Stage B adds a verifiable-quote guardrail (verify_quotes): every quoted span in a
draft must match the CORRECTED transcript text attached to the packet, or the
audit hard-fails. This makes fabricated quotes structurally catchable; speaker
attribution is flagged for mandatory human/external review.
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any

from ingestion.cache import iso_utc
from newsroom.common import (
    DEFAULT_CLAIM_AUDIT_DIR,
    PROJECT_ROOT,
    TEAM_ABBR,
    TEAM_ID,
    TEAM_NAME,
    _dedupe_strings,
    _display_date,
    _display_path,
    _load_assets_from_paths,
    _opponent_team,
    _team_by_id,
)
from newsroom.drafts import render_markdown_draft
from newsroom.schemas import (
    CLAIM_AUDIT_CATEGORIES,
    CLAIM_AUDIT_WARNING_CATEGORIES,
    CLAIM_SUPPORT_STATUSES,
    validate_claim_evidence_audit,
)

ASSET_AUDIT_ORDER = (
    "short_recap",
    "takeaways",
    "push_alert",
    "newsletter_blurb",
    "seo_summary",
    "social_caption",
    "headline_candidates",
)

UNSUPPORTED_INTERPRETATION_MARKERS = (
    "wanted it more",
    "did not care",
    "didn't care",
    "proved that",
    "proves that",
    "showed who they are",
    "because of effort",
    "coach decided",
    "locker room",
    "huddle",
    "halftime speech",
    "body language",
    "established the terms",
    "established their own rhythm",
    "teaching points",
)

MEMORY_STYLE_MARKERS = (
    "season-long",
    "trend",
    "identity",
    "culture",
    "habit",
    "habits",
    "development",
)

EDITORIAL_RULE_MARKERS = (
    "not proof",
    "does not make the game about one minute",
    "does not turn the result into a statement about effort or intent",
    "does not reduce the game to one bad minute",
    "none of those numbers needs embellishment",
    "none of those numbers needs extra drama",
    "treat with care",
)

GROUNDING_METHOD_VERSION = "deterministic-sentence-grounding/v0.1"


def format_claim_evidence_audit(
    packet: dict[str, Any],
    *,
    article_markdown: str | None = None,
    article_markdown_path: Path | str | None = None,
    packet_path: Path | str | None = None,
    assets: dict[str, Any] | None = None,
    asset_paths: dict[str, Path | str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a local, advisory claim evidence audit from packet facts and generated copy."""
    if article_markdown is None and article_markdown_path and Path(article_markdown_path).exists():
        article_markdown = Path(article_markdown_path).read_text()
    article_markdown = article_markdown or render_markdown_draft(packet)

    asset_paths = asset_paths or {}
    if assets is None and asset_paths:
        assets = _load_assets_from_paths(asset_paths)
    assets = assets or {}

    items = [
        {
            "item_key": "main_article",
            "label": "Main article draft",
            "path": _display_path(article_markdown_path) if article_markdown_path else None,
            "text": _main_article_text(article_markdown),
        }
    ]
    for item_key in ASSET_AUDIT_ORDER:
        if item_key in assets:
            items.append(
                {
                    "item_key": item_key,
                    "label": _item_label(item_key),
                    "path": _display_path(asset_paths[item_key]) if item_key in asset_paths else None,
                    "text": _item_text(item_key, assets[item_key]),
                }
            )

    source_inventory = _source_inventory(packet)
    claims: list[dict[str, Any]] = []
    for item in items:
        claims.extend(_audit_item(packet, item))
    claims.extend(_source_gap_claims(source_inventory))

    sentence_map = _sentence_map(packet, items)
    sentence_summary = _sentence_summary(sentence_map)
    all_text = "\n".join(item["text"] for item in items)
    summary = _audit_summary(packet, claims, source_inventory, all_text)
    audit = {
        "schema_version": "mystics-claim-evidence-audit/v0.2",
        "event_id": packet["game"]["id"],
        "generation_timestamp": generated_at or iso_utc(),
        "claim_categories": list(CLAIM_AUDIT_CATEGORIES),
        "support_statuses": list(CLAIM_SUPPORT_STATUSES),
        "grounding_method_version": GROUNDING_METHOD_VERSION,
        "article_markdown_path": _display_path(article_markdown_path) if article_markdown_path else None,
        "packet_path": _display_path(packet_path) if packet_path else None,
        "asset_paths": {key: _display_path(path) for key, path in sorted(asset_paths.items())},
        "source_inventory": source_inventory,
        "claims": claims,
        "sentence_map": sentence_map,
        "summary": summary,
        "sentence_summary": sentence_summary,
        "quote_verification": verify_quotes(_main_article_text(article_markdown), packet),
        "name_validation": validate_person_names(packet, _main_article_text(article_markdown)),
        "advisory_only": True,
        "human_editor_required": True,
        "no_auto_publish": True,
    }
    return validate_claim_evidence_audit(audit)


def write_claim_evidence_audit(
    packet: dict[str, Any],
    *,
    article_markdown_path: Path | str,
    packet_path: Path | str,
    audit_dir: Path = DEFAULT_CLAIM_AUDIT_DIR,
    assets: dict[str, Any] | None = None,
    asset_paths: dict[str, Path | str] | None = None,
    generated_at: str | None = None,
) -> Path:
    """Write the advisory claim evidence audit JSON. This does not publish."""
    audit_dir.mkdir(parents=True, exist_ok=True)
    event_id = packet["game"]["id"]
    audit_path = audit_dir / f"mystics-claim-audit-{event_id}.json"
    audit = format_claim_evidence_audit(
        packet,
        article_markdown_path=article_markdown_path,
        packet_path=packet_path,
        assets=assets,
        asset_paths=asset_paths,
        generated_at=generated_at,
    )
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    return audit_path


def load_claim_evidence_audit(path: Path | str, *, event_id: str | None = None) -> dict[str, Any]:
    """Load, validate, and optionally event-match a persisted claim audit."""
    audit_path = Path(path)
    if not audit_path.is_absolute():
        audit_path = PROJECT_ROOT / audit_path
    try:
        audit = json.loads(audit_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read claim evidence audit at {audit_path}: {exc}") from exc
    if not isinstance(audit, dict):
        raise ValueError(f"Invalid claim evidence audit at {audit_path}: artifact must be a JSON object")
    try:
        validate_claim_evidence_audit(audit)
    except ValueError as exc:
        raise ValueError(f"Invalid claim evidence audit at {audit_path}: {exc}") from exc
    if event_id is not None and str(audit.get("event_id") or "") != str(event_id):
        raise ValueError(
            f"claim evidence audit at {audit_path} has event_id {audit.get('event_id')!r}; "
            f"expected active packet event_id {str(event_id)!r}"
        )
    return audit


def _preview_claim_audit_path(packet: dict[str, Any], audit_dir: Path) -> Path:
    return audit_dir / f"mystics-claim-audit-{packet['game']['id']}.json"


def _audit_item(packet: dict[str, Any], item: dict[str, Any]) -> list[dict[str, Any]]:
    text = item["text"]
    lower = text.lower()
    item_key = item["item_key"]
    claims: list[dict[str, Any]] = []
    narrative = packet.get("narrative") or {}
    game = packet.get("game") or {}
    opponent = _opponent_team(game.get("teams") or [])
    mystics = _team_by_id(game.get("teams") or [], TEAM_ID)
    best_mystic = _best_mystics_performer(packet)

    final_score = str(narrative.get("final_score") or "")
    if final_score and final_score.lower() in lower:
        claims.append(
            _claim(
                item_key,
                f"{item['label']} states the official final score.",
                "supported_by_packet",
                ["narrative.final_score", "game.teams[].score"],
                [final_score],
            )
        )
    elif item_key in {"main_article", "short_recap", "push_alert", "newsletter_blurb", "seo_summary", "social_caption"}:
        claims.append(
            _claim(
                item_key,
                f"{item['label']} does not clearly surface the final score.",
                "needs_human_review",
                ["narrative.final_score"],
                ["Score-bearing recap items should make the official final easy to verify."],
            )
        )

    score_phrase = f"{opponent.get('score')}-{mystics.get('score')}"
    if score_phrase in lower and narrative.get("result") == "loss":
        claims.append(
            _claim(
                item_key,
                f"{item['label']} states Washington's game result.",
                "supported_by_packet",
                ["game.teams[].winner", "game.teams[].score", "narrative.result"],
                [f"Washington loss shown by score {score_phrase}."],
            )
        )

    venue = str(game.get("venue") or "")
    if venue and venue.lower() in lower:
        claims.append(_packet_claim(item_key, item["label"], "venue", "game.venue", venue))

    run = narrative.get("biggest_scoring_run") or {}
    run_summary = str(run.get("summary") or "")
    if run_summary and run_summary.lower() in lower:
        claims.append(_packet_claim(item_key, item["label"], "biggest scoring run", "narrative.biggest_scoring_run.summary", run_summary))

    key = narrative.get("key_quarter_or_turning_point") or {}
    key_summary = str(key.get("summary") or "")
    if key_summary and key_summary.lower() in lower:
        claims.append(
            _packet_claim(
                item_key,
                item["label"],
                "key quarter or turning point",
                "narrative.key_quarter_or_turning_point.summary",
                key_summary,
            )
        )

    claims.extend(_stat_edge_claims(item_key, item["label"], lower, narrative.get("stat_edges") or {}))

    selected_angle = (packet.get("story_angles") or [{}])[0]
    if _contains_any(lower, [selected_angle.get("angle_title"), selected_angle.get("angle_summary")]):
        claims.append(
            _claim(
                item_key,
                f"{item['label']} uses the selected story angle.",
                "supported_by_packet",
                ["story_angles[0]", "story_angles[0].supporting_signals"],
                ["Selected angle is derived from normalized packet facts plus risk flags."],
            )
        )
        if any(str(signal).startswith("Memory context:") for signal in selected_angle.get("supporting_signals") or []):
            claims.append(
                _claim(
                    item_key,
                    f"{item['label']} carries memory-context framing from the selected angle.",
                    "supported_by_memory",
                    ["story_angles[0].supporting_signals", "memory"],
                    ["Memory is context only; editor should verify it is not presented as current-game fact."],
                )
            )

    if best_mystic and str(best_mystic.get("player") or "").lower() in lower:
        claims.append(
            _claim(
                item_key,
                f"{item['label']} surfaces the top Mystics performer.",
                "supported_by_packet",
                [_performer_path(packet, best_mystic)],
                [f"{best_mystic.get('player')} - {best_mystic.get('stat_line')}"],
            )
        )
    elif item_key in {"main_article", "short_recap", "takeaways", "newsletter_blurb"}:
        claims.append(
            _claim(
                item_key,
                f"{item['label']} does not clearly surface the top Mystics performer.",
                "needs_human_review",
                ["narrative.top_performers"],
                ["Mystics beat handoff should make Washington's leading line easy to find."],
            )
        )

    for marker in _unsupported_markers(lower):
        claims.append(
            _claim(
                item_key,
                f"{item['label']} contains unsupported interpretation marker: {marker}",
                "unsupported",
                [],
                ["Deterministic marker; editor should verify whether packet facts support the phrasing."],
            )
        )

    if _memory_style_language(lower):
        claims.append(
            _claim(
                item_key,
                f"{item['label']} uses memory-style or trend language.",
                "supported_by_memory",
                ["memory", "story_angles[].risk_flags"],
                ["Treat this as editorial context unless the current packet explicitly supports the claim."],
            )
        )

    washington_mentions, opponent_mentions = _mention_counts(packet, text)
    if opponent_mentions >= 4 and opponent_mentions > max(2, int(washington_mentions * 1.4)):
        claims.append(
            _claim(
                item_key,
                f"{item['label']} appears opponent-heavy for a Mystics beat handoff.",
                "balance_warning",
                ["narrative.top_performers", "game.teams"],
                [f"Washington/Mystics mentions: {washington_mentions}; opponent mentions: {opponent_mentions}."],
            )
        )
    return claims


def _source_gap_claims(source_inventory: dict[str, Any]) -> list[dict[str, Any]]:
    if source_inventory["second_source_present"]:
        return []
    return [
        _claim(
            "source_inventory",
            "Packet source coverage is ESPN-only; no independent second source is present.",
            "source_gap",
            ["sources"],
            ["Use as a review warning, not a generation blocker."],
        )
    ]


def _sentence_map(packet: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        sentence_number = 1
        for section, sentence in _sentences_for_item(item):
            rows.append(_ground_sentence(packet, item["item_key"], section, sentence, sentence_number))
            sentence_number += 1
    return rows


def _ground_sentence(
    packet: dict[str, Any],
    item_key: str,
    section: str,
    sentence: str,
    sentence_number: int,
) -> dict[str, Any]:
    lower = sentence.lower()
    claim_types: list[str] = []
    evidence_refs: list[dict[str, str]] = []
    risk_flags: list[str] = []
    notes: list[str] = []
    confidence_values: list[float] = []

    contradictions = _contradictions_for_sentence(packet, sentence)
    for contradiction in contradictions:
        claim_types.extend(contradiction["claim_types"])
        evidence_refs.extend(contradiction["evidence_refs"])
        notes.append(contradiction["note"])

    _match_score_result(packet, lower, claim_types, evidence_refs, confidence_values)
    _match_venue_date(packet, sentence, lower, claim_types, evidence_refs, confidence_values)
    _match_player_stats(packet, sentence, lower, claim_types, evidence_refs, confidence_values)
    _match_team_stat_edges(packet, lower, claim_types, evidence_refs, confidence_values)
    _match_game_flow(packet, lower, claim_types, evidence_refs, confidence_values)
    _match_selected_angle(packet, lower, claim_types, evidence_refs, confidence_values)

    unsupported_markers = _unsupported_markers(lower)
    if unsupported_markers:
        claim_types.append("unsupported_interpretation")
        risk_flags.extend(f"unsupported_marker:{marker}" for marker in unsupported_markers)
        notes.append("Sentence contains deterministic unsupported-interpretation marker.")

    memory_style = _memory_style_language(lower)
    if memory_style:
        claim_types.append("memory_or_trend_language")
        evidence_refs.append(_evidence_ref("memory", "Persistent memory is editorial context only.", "memory"))
        risk_flags.append("memory_or_trend_language")
        notes.append("Trend or memory-style language should be treated as weak support unless the current packet proves it.")

    editorial_rule = _editorial_rule_sentence(lower)
    if editorial_rule:
        claim_types.append("editorial_rule")
        evidence_refs.append(
            _evidence_ref(
                "memory.editorial_rules.rules",
                "Deterministic editorial guardrail against overclaiming.",
                "editorial_rule",
            )
        )
        notes.append("Sentence is grounded as an editorial guardrail rather than a game fact.")

    interpretive = _interpretive_without_direct_evidence(packet, lower, evidence_refs)
    if interpretive:
        claim_types.append("editorial_framing")
        risk_flags.append("weak_interpretive_claim")
        notes.append("Sentence uses interpretive game framing without a direct packet-value match.")

    if contradictions:
        support_status = "contradiction"
        support_confidence = 0.05
        risk_flags.append("contradiction")
    elif unsupported_markers:
        support_status = "unsupported"
        support_confidence = 0.15
    elif memory_style:
        support_status = "weak"
        support_confidence = 0.45
    elif editorial_rule:
        support_status = "editorial_rule"
        support_confidence = 0.9
    elif evidence_refs:
        support_status = "supported"
        support_confidence = max(confidence_values or [0.86])
    elif interpretive:
        support_status = "weak"
        support_confidence = 0.5
    else:
        support_status = "not_claim"
        support_confidence = 1.0
        notes.append("No deterministic claim matcher fired for this sentence.")

    sentence_id = f"{item_key}:s{sentence_number:03d}"
    return {
        "sentence_id": sentence_id,
        "item_key": item_key,
        "section": section,
        "text": sentence,
        "claim_types": _dedupe_strings(claim_types),
        "support_status": support_status,
        "support_confidence": round(support_confidence, 2),
        "evidence_refs": _dedupe_evidence_refs(evidence_refs),
        "risk_flags": _dedupe_strings(risk_flags),
        "notes": _dedupe_strings(notes),
    }


def _sentence_summary(sentence_map: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = {status: 0 for status in CLAIM_SUPPORT_STATUSES}
    for sentence in sentence_map:
        status = sentence.get("support_status")
        if status in status_counts:
            status_counts[status] += 1
    lowest = sorted(
        [sentence for sentence in sentence_map if sentence.get("support_status") != "not_claim"],
        key=lambda sentence: (float(sentence.get("support_confidence") or 0), sentence.get("sentence_id") or ""),
    )[:5]
    return {
        "total_sentences": len(sentence_map),
        "claim_sentence_count": sum(
            1
            for sentence in sentence_map
            if sentence.get("support_status") != "not_claim"
        ),
        "status_counts": status_counts,
        "unsupported_sentence_count": status_counts["unsupported"],
        "weak_sentence_count": status_counts["weak"],
        "contradiction_count": status_counts["contradiction"],
        "editorial_rule_sentence_count": status_counts["editorial_rule"],
        "lowest_confidence_sentence_ids": [
            str(sentence.get("sentence_id"))
            for sentence in lowest
        ],
    }


def _stat_edge_claims(item_key: str, label: str, lower: str, edges: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for edge_key, markers in (
        ("turnovers", ("turnover", "turnovers")),
        ("rebounds", ("rebound", "rebounds", "glass")),
        ("bench_points", ("bench",)),
        ("three_point_makes", ("3pt", "three-point", "three point")),
    ):
        edge = edges.get(edge_key) or {}
        if not isinstance(edge, dict) or not any(marker in lower for marker in markers):
            continue
        values = [str(edge.get("mystics")), str(edge.get("opponent"))]
        if all(value and value != "None" and value.lower() in lower for value in values):
            out.append(
                _claim(
                    item_key,
                    f"{label} states the {edge_key.replace('_', ' ')} split.",
                    "supported_by_packet",
                    [f"narrative.stat_edges.{edge_key}"],
                    [f"Washington {values[0]} vs opponent {values[1]}."],
                )
            )
    return out


def _audit_summary(
    packet: dict[str, Any],
    claims: list[dict[str, Any]],
    source_inventory: dict[str, Any],
    all_text: str,
) -> dict[str, Any]:
    counts = {category: 0 for category in CLAIM_AUDIT_CATEGORIES}
    for claim in claims:
        category = claim.get("category")
        if category in counts:
            counts[category] += 1
    washington_mentions, opponent_mentions = _mention_counts(packet, all_text)
    best_mystic = _best_mystics_performer(packet)
    best_name = str(best_mystic.get("player") or "")
    warning_count = sum(counts[category] for category in CLAIM_AUDIT_WARNING_CATEGORIES)
    return {
        "total_claims": len(claims),
        "category_counts": counts,
        "source_count": source_inventory["source_count"],
        "second_source_present": source_inventory["second_source_present"],
        "washington_mentions": washington_mentions,
        "opponent_mentions": opponent_mentions,
        "top_mystics_performer": best_name,
        "top_mystics_performer_surfaced": bool(best_name and best_name.lower() in all_text.lower()),
        "warning_count": warning_count,
    }


def _source_inventory(packet: dict[str, Any]) -> dict[str, Any]:
    sources = []
    families = []
    for source in packet.get("sources") or []:
        name = str(source.get("name") or "")
        url = str(source.get("url") or "")
        family = _source_family(name, url)
        families.append(family)
        sources.append({"name": name, "url": url, "family": family})
    unique_families = _dedupe_strings(families)
    non_espn_families = [family for family in unique_families if family != "ESPN"]
    return {
        "source_count": len(sources),
        "source_families": unique_families,
        "second_source_present": bool(non_espn_families),
        "sources": sources,
    }


def _source_family(name: str, url: str) -> str:
    lower = f"{name} {url}".lower()
    if "espn" in lower:
        return "ESPN"
    if "wnba.com" in lower:
        return "WNBA.com"
    if "mystics" in lower:
        return "Mystics official"
    return name.split()[0] if name else "Unknown"


def _sentences_for_item(item: dict[str, Any]) -> list[tuple[str, str]]:
    item_key = item["item_key"]
    section = "body" if item_key == "main_article" else "asset"
    if item_key == "headline_candidates":
        section = "headline"

    rows: list[tuple[str, str]] = []
    for raw_line in str(item.get("text") or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("**By "):
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        for sentence in _split_sentences(line):
            if sentence:
                rows.append((section, sentence))
    return rows


def _split_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“])", cleaned)
    return [part.strip() for part in parts if part.strip()]


def _match_score_result(
    packet: dict[str, Any],
    lower: str,
    claim_types: list[str],
    evidence_refs: list[dict[str, str]],
    confidence_values: list[float],
) -> None:
    narrative = packet.get("narrative") or {}
    final_score = str(narrative.get("final_score") or "")
    if final_score and (final_score.lower() in lower or _has_expected_score_pair(packet, lower)):
        claim_types.append("final_score")
        evidence_refs.append(_evidence_ref("narrative.final_score", final_score))
        confidence_values.append(0.96)

    result = str(narrative.get("result") or "")
    if result and _sentence_states_result(packet, lower, result):
        claim_types.append("result")
        evidence_refs.append(_evidence_ref("narrative.result", result))
        confidence_values.append(0.9)


def _match_venue_date(
    packet: dict[str, Any],
    sentence: str,
    lower: str,
    claim_types: list[str],
    evidence_refs: list[dict[str, str]],
    confidence_values: list[float],
) -> None:
    game = packet.get("game") or {}
    venue = str(game.get("venue") or "")
    if venue and venue.lower() in lower:
        claim_types.append("venue")
        evidence_refs.append(_evidence_ref("game.venue", venue))
        confidence_values.append(0.92)

    display_date = _display_date(game.get("date"))
    iso_date = str(game.get("date") or "")[:10]
    if (display_date and display_date.lower() in lower) or (iso_date and iso_date in sentence):
        claim_types.append("date")
        evidence_refs.append(_evidence_ref("game.date", str(game.get("date") or "")))
        confidence_values.append(0.92)


def _match_player_stats(
    packet: dict[str, Any],
    sentence: str,
    lower: str,
    claim_types: list[str],
    evidence_refs: list[dict[str, str]],
    confidence_values: list[float],
) -> None:
    performers = (packet.get("narrative") or {}).get("top_performers") or []
    best_mystic = _best_mystics_performer(packet)
    for index, performer in enumerate(performers):
        player = str(performer.get("player") or "")
        if not player or player.lower() not in lower:
            continue
        claim_types.append("player_stat")
        if performer.get("team") == TEAM_NAME and performer.get("player") == best_mystic.get("player"):
            claim_types.append("top_mystics_performer")
        evidence_refs.append(_evidence_ref(f"narrative.top_performers[{index}]", _player_evidence_value(performer)))
        stat_line = str(performer.get("stat_line") or "")
        confidence_values.append(0.94 if stat_line and stat_line.lower() in lower else 0.82)


def _match_team_stat_edges(
    packet: dict[str, Any],
    lower: str,
    claim_types: list[str],
    evidence_refs: list[dict[str, str]],
    confidence_values: list[float],
) -> None:
    edges = (packet.get("narrative") or {}).get("stat_edges") or {}
    for edge_key, markers in _stat_edge_markers():
        edge = edges.get(edge_key) or {}
        if not isinstance(edge, dict) or not any(marker in lower for marker in markers):
            continue
        values = [str(edge.get("mystics")), str(edge.get("opponent"))]
        if all(value and value != "None" and value.lower() in lower for value in values):
            claim_types.append("team_stat")
            evidence_refs.append(_evidence_ref(f"narrative.stat_edges.{edge_key}", _edge_evidence_value(edge_key, edge)))
            confidence_values.append(0.91)


def _match_game_flow(
    packet: dict[str, Any],
    lower: str,
    claim_types: list[str],
    evidence_refs: list[dict[str, str]],
    confidence_values: list[float],
) -> None:
    narrative = packet.get("narrative") or {}
    run = narrative.get("biggest_scoring_run") or {}
    run_summary = str(run.get("summary") or "")
    if run_summary and run_summary.lower() in lower:
        claim_types.append("scoring_run")
        evidence_refs.append(_evidence_ref("narrative.biggest_scoring_run.summary", run_summary))
        confidence_values.append(0.94)

    key = narrative.get("key_quarter_or_turning_point") or {}
    key_summary = str(key.get("summary") or "")
    if key_summary and key_summary.lower() in lower:
        claim_types.append("key_quarter")
        evidence_refs.append(_evidence_ref("narrative.key_quarter_or_turning_point.summary", key_summary))
        confidence_values.append(0.94)


def _match_selected_angle(
    packet: dict[str, Any],
    lower: str,
    claim_types: list[str],
    evidence_refs: list[dict[str, str]],
    confidence_values: list[float],
) -> None:
    selected = (packet.get("story_angles") or [{}])[0]
    if not isinstance(selected, dict):
        return
    title = str(selected.get("angle_title") or "")
    summary = str(selected.get("angle_summary") or "")
    if (title and title.lower() in lower) or (summary and summary.lower() in lower):
        claim_types.append("selected_story_angle")
        evidence_refs.append(_evidence_ref("story_angles[0]", title or summary))
        confidence_values.append(0.78)


def _contradictions_for_sentence(packet: dict[str, Any], sentence: str) -> list[dict[str, Any]]:
    contradictions: list[dict[str, Any]] = []
    lower = sentence.lower()
    contradictions.extend(_score_result_contradictions(packet, lower))
    contradictions.extend(_venue_contradictions(packet, sentence, lower))
    contradictions.extend(_date_contradictions(packet, sentence, lower))
    contradictions.extend(_player_stat_contradictions(packet, sentence, lower))
    contradictions.extend(_team_stat_contradictions(packet, lower))
    return contradictions


def _score_result_contradictions(packet: dict[str, Any], lower: str) -> list[dict[str, Any]]:
    narrative = packet.get("narrative") or {}
    result = str(narrative.get("result") or "")
    contradictions: list[dict[str, Any]] = []
    if result == "loss" and _sentence_states_result(packet, lower, "win"):
        contradictions.append(
            _contradiction("result", "Sentence states a Washington win, but the packet result is a loss.", "narrative.result", result)
        )
    if result == "win" and _sentence_states_result(packet, lower, "loss"):
        contradictions.append(
            _contradiction("result", "Sentence states a Washington loss, but the packet result is a win.", "narrative.result", result)
        )

    if _score_context(packet, lower):
        expected_scores = _expected_score_values(packet)
        mentioned_scores = _score_like_numbers(lower)
        if len(mentioned_scores) >= 2 and any(score not in expected_scores for score in mentioned_scores[:2]):
            contradictions.append(
                _contradiction(
                    "final_score",
                    "Sentence contains an obvious score value that does not match the packet final.",
                    "narrative.final_score",
                    str(narrative.get("final_score") or ""),
                )
            )
    return contradictions


def _venue_contradictions(packet: dict[str, Any], sentence: str, lower: str) -> list[dict[str, Any]]:
    venue = str((packet.get("game") or {}).get("venue") or "")
    if not venue or venue.lower() in lower or " at " not in lower:
        return []
    pattern = r"\bat\s+([A-Z][A-Za-z0-9&'. -]+(?:Arena|Center|Fieldhouse|Pavilion|Stadium|Coliseum))\b"
    for match in re.finditer(pattern, sentence):
        stated = match.group(1).strip()
        if stated and stated.lower() != venue.lower():
            return [
                _contradiction(
                    "venue",
                    f"Sentence states venue {stated}, but the packet venue is {venue}.",
                    "game.venue",
                    venue,
                )
            ]
    return []


def _date_contradictions(packet: dict[str, Any], sentence: str, lower: str) -> list[dict[str, Any]]:
    game = packet.get("game") or {}
    actual_display = _display_date(game.get("date"))
    if actual_display and actual_display.lower() in lower:
        return []
    if any(marker in lower for marker in ("next listed game", "next game", "schedule", "previous game")):
        return []
    month_pattern = (
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December) "
        r"\d{1,2}, \d{4}\b"
    )
    if not _game_context(packet, lower):
        return []
    for match in re.finditer(month_pattern, sentence):
        stated = match.group(0)
        if stated.lower() != actual_display.lower():
            return [
                _contradiction(
                    "date",
                    f"Sentence states date {stated}, but the packet date is {actual_display}.",
                    "game.date",
                    str(game.get("date") or ""),
                )
            ]
    return []


def _player_stat_contradictions(packet: dict[str, Any], sentence: str, lower: str) -> list[dict[str, Any]]:
    performers = (packet.get("narrative") or {}).get("top_performers") or []
    player_names = [str(performer.get("player") or "") for performer in performers if performer.get("player")]
    contradictions: list[dict[str, Any]] = []
    for index, performer in enumerate(performers):
        player = str(performer.get("player") or "")
        if not player or player.lower() not in lower:
            continue
        player_window = _player_sentence_window(sentence, player, player_names)
        window_lower = player_window.lower()
        for stat_key, labels in (
            ("points", ("point", "points")),
            ("rebounds", ("rebound", "rebounds")),
            ("assists", ("assist", "assists")),
        ):
            actual = performer.get(stat_key)
            if not isinstance(actual, int):
                continue
            for label in labels:
                for match in re.finditer(rf"\b(\d{{1,2}})\s+{label}\b", window_lower):
                    stated = int(match.group(1))
                    if stated != actual:
                        contradictions.append(
                            _contradiction(
                                "player_stat",
                                f"Sentence gives {player} {stated} {label}, but the packet has {actual}.",
                                f"narrative.top_performers[{index}].{stat_key}",
                                str(actual),
                            )
                        )
    return contradictions


def _team_stat_contradictions(packet: dict[str, Any], lower: str) -> list[dict[str, Any]]:
    edges = (packet.get("narrative") or {}).get("stat_edges") or {}
    contradictions: list[dict[str, Any]] = []
    team_terms = ("washington", "mystics", TEAM_ABBR.lower())
    for edge_key, markers in _stat_edge_markers():
        edge = edges.get(edge_key) or {}
        if not isinstance(edge, dict) or not any(marker in lower for marker in markers):
            continue
        mystics_value = edge.get("mystics")
        if not isinstance(mystics_value, int):
            continue
        if not any(term in lower for term in team_terms):
            continue
        team_stat_context = any(
            f"{team} {verb}" in lower
            for team in team_terms
            for verb in ("had", "finished with", "committed", "grabbed", "totaled", "posted", "recorded")
        )
        if not team_stat_context:
            continue
        for marker in markers:
            pattern = rf"\b(?:washington|mystics|{re.escape(TEAM_ABBR.lower())})\b[^.]{{0,45}}?\b(\d{{1,3}})\s+(?:total\s+)?{re.escape(marker)}\b"
            for match in re.finditer(pattern, lower):
                stated = int(match.group(1))
                if stated != mystics_value:
                    contradictions.append(
                        _contradiction(
                            "team_stat",
                            f"Sentence gives Washington {stated} {marker}, but the packet has {mystics_value}.",
                            f"narrative.stat_edges.{edge_key}.mystics",
                            str(mystics_value),
                        )
                    )
    return contradictions


def _main_article_text(markdown: str) -> str:
    text = re.sub(r"^---.*?---\s*", "", markdown, flags=re.DOTALL)
    if "**Excerpt:**" in text:
        text = text.split("**Excerpt:**", 1)[0]
    return text.strip()


def _item_text(item_key: str, content: Any) -> str:
    if item_key == "takeaways" and isinstance(content, list):
        return "\n".join(
            f"{item.get('title', '')}: {item.get('explanation', '')}"
            for item in content
            if isinstance(item, dict)
        )
    if item_key == "headline_candidates" and isinstance(content, list):
        return "\n".join(
            str(item.get("headline", ""))
            for item in content
            if isinstance(item, dict)
        )
    if isinstance(content, (dict, list)):
        return json.dumps(content, sort_keys=True)
    return str(content or "")


def _item_label(item_key: str) -> str:
    return item_key.replace("_", " ").title()


def _packet_claim(item_key: str, label: str, claim_label: str, evidence_path: str, evidence_value: str) -> dict[str, Any]:
    return _claim(
        item_key,
        f"{label} states the {claim_label}.",
        "supported_by_packet",
        [evidence_path],
        [evidence_value],
    )


def _claim(
    item_key: str,
    claim: str,
    category: str,
    evidence_paths: list[str],
    notes: list[str],
) -> dict[str, Any]:
    return {
        "item_key": item_key,
        "claim": claim,
        "category": category,
        "evidence_paths": evidence_paths,
        "notes": notes,
    }


def _evidence_ref(path: str, value: Any, source_family: str = "packet") -> dict[str, str]:
    return {
        "path": path,
        "value": str(value),
        "source_family": source_family,
    }


def _dedupe_evidence_refs(values: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen = set()
    for value in values:
        key = (value.get("path", ""), value.get("value", ""), value.get("source_family", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _contradiction(claim_type: str, note: str, evidence_path: str, evidence_value: Any) -> dict[str, Any]:
    return {
        "claim_types": [claim_type],
        "evidence_refs": [_evidence_ref(evidence_path, evidence_value)],
        "note": note,
    }


def _stat_edge_markers() -> tuple[tuple[str, tuple[str, ...]], ...]:
    return (
        ("turnovers", ("turnover", "turnovers")),
        ("rebounds", ("rebound", "rebounds", "glass")),
        ("bench_points", ("bench", "bench scoring", "bench-scoring")),
        ("three_point_makes", ("3pt", "three-point", "three point", "three-point line")),
        ("points_in_paint", ("paint", "points in the paint")),
    )


def _edge_evidence_value(edge_key: str, edge: dict[str, Any]) -> str:
    return (
        f"{edge_key.replace('_', ' ')}: Washington {edge.get('mystics')} "
        f"vs opponent {edge.get('opponent')} (edge: {edge.get('edge')})."
    )


def _player_evidence_value(performer: dict[str, Any]) -> str:
    return (
        f"{performer.get('player')} ({performer.get('team')}) - "
        f"{performer.get('stat_line', 'stat line unavailable')}"
    )


def _sentence_states_result(packet: dict[str, Any], lower: str, result: str) -> bool:
    opponent = _opponent_team((packet.get("game") or {}).get("teams") or [])
    opponent_terms = _opponent_terms(opponent)
    washington_terms = ("washington", "mystics")
    if result == "win":
        win_verbs = ("beat", "defeated", "topped", "handled", "won")
        return any(
            f"{team} {verb}" in lower and any(opp in lower for opp in opponent_terms)
            for team in washington_terms
            for verb in win_verbs
        )
    if result == "loss":
        loss_phrases = ("lost to", "fell to", "lost against")
        return any(
            f"{team} {phrase}" in lower and any(opp in lower for opp in opponent_terms)
            for team in washington_terms
            for phrase in loss_phrases
        )
    return False


def _opponent_terms(opponent: dict[str, Any]) -> tuple[str, ...]:
    name = str(opponent.get("name") or "").lower()
    short_name = name.replace("washington ", "")
    abbreviation = str(opponent.get("abbreviation") or "").lower()
    return tuple(term for term in (name, short_name, abbreviation) if term)


def _has_expected_score_pair(packet: dict[str, Any], lower: str) -> bool:
    if not _score_context(packet, lower):
        return False
    expected_scores = _expected_score_values(packet)
    mentioned_scores = _score_like_numbers(lower)
    return len(mentioned_scores) >= 2 and set(mentioned_scores[:2]) == expected_scores


def _score_context(packet: dict[str, Any], lower: str) -> bool:
    return "final" in lower or _game_context(packet, lower) or "lost to" in lower or "beat" in lower or "fell to" in lower


def _game_context(packet: dict[str, Any], lower: str) -> bool:
    game = packet.get("game") or {}
    opponent = _opponent_team(game.get("teams") or [])
    terms = ["washington", "mystics", TEAM_ABBR.lower(), *_opponent_terms(opponent)]
    return sum(1 for term in _dedupe_strings(terms) if term and term in lower) >= 2


def _expected_score_values(packet: dict[str, Any]) -> set[int]:
    scores = set()
    for team in ((packet.get("game") or {}).get("teams") or []):
        score = team.get("score")
        if isinstance(score, int):
            scores.add(score)
    return scores


def _score_like_numbers(lower: str) -> list[int]:
    return [
        int(match.group(0))
        for match in re.finditer(r"\b\d{2,3}\b", lower)
        if 40 <= int(match.group(0)) <= 160
    ]


def _player_sentence_window(sentence: str, player: str, player_names: list[str]) -> str:
    lower = sentence.lower()
    start = lower.find(player.lower())
    if start == -1:
        return sentence
    end = len(sentence)
    for other in player_names:
        if other == player:
            continue
        other_index = lower.find(other.lower(), start + len(player))
        if other_index != -1:
            end = min(end, other_index)
    return sentence[start:end]


def _editorial_rule_sentence(lower: str) -> bool:
    return any(marker in lower for marker in EDITORIAL_RULE_MARKERS)


def _interpretive_without_direct_evidence(packet: dict[str, Any], lower: str, evidence_refs: list[dict[str, str]]) -> bool:
    if evidence_refs or not _game_context(packet, lower):
        return False
    markers = (
        "control",
        "pressure",
        "tone",
        "shape",
        "frame",
        "chase",
        "response",
        "margin",
        "steady",
        "resistance",
        "command",
        "difficult",
        "clean takeaway",
    )
    return any(marker in lower for marker in markers)


def _contains_any(lower_text: str, values: list[Any]) -> bool:
    return any(str(value or "").strip() and str(value).lower() in lower_text for value in values)


def _best_mystics_performer(packet: dict[str, Any]) -> dict[str, Any]:
    for performer in (packet.get("narrative") or {}).get("top_performers") or []:
        if performer.get("team") == TEAM_NAME:
            return performer
    return {}


def _performer_path(packet: dict[str, Any], performer: dict[str, Any]) -> str:
    performers = (packet.get("narrative") or {}).get("top_performers") or []
    for index, item in enumerate(performers):
        if item is performer or item.get("player") == performer.get("player"):
            return f"narrative.top_performers[{index}]"
    return "narrative.top_performers"


def _unsupported_markers(lower_text: str) -> list[str]:
    found = []
    for marker in UNSUPPORTED_INTERPRETATION_MARKERS:
        index = lower_text.find(marker)
        if index == -1:
            continue
        window = lower_text[max(0, index - 44) : index + len(marker) + 44]
        if any(safe in window for safe in ("do not", "avoid", "without", "not add", "not proof", "no ")):
            continue
        found.append(marker)
    return found


def _memory_style_language(lower_text: str) -> bool:
    return any(marker in lower_text for marker in MEMORY_STYLE_MARKERS)


def _mention_counts(packet: dict[str, Any], text: str) -> tuple[int, int]:
    lower = text.lower()
    opponent = _opponent_team((packet.get("game") or {}).get("teams") or [])
    washington_terms = ["washington", "mystics", TEAM_ABBR.lower()]
    opponent_terms = [
        str(opponent.get("name") or ""),
        str(opponent.get("name") or "").replace("Washington ", ""),
        str(opponent.get("abbreviation") or ""),
    ]
    for performer in (packet.get("narrative") or {}).get("top_performers") or []:
        name = str(performer.get("player") or "")
        if not name:
            continue
        if performer.get("team") == TEAM_NAME:
            washington_terms.append(name)
        else:
            opponent_terms.append(name)
    return _count_terms(lower, washington_terms), _count_terms(lower, opponent_terms)


def _count_terms(lower_text: str, terms: list[str]) -> int:
    count = 0
    for term in _dedupe_strings([str(term).lower() for term in terms if str(term).strip()]):
        count += len(re.findall(rf"\b{re.escape(term)}\b", lower_text))
    return count


# ── Verifiable-quote guardrail (Stage B) ──────────────────────────────────────
#
# Every quoted span in a draft must match the CORRECTED transcript text attached
# to the packet (string verification is the HARD gate). Any quote that names a
# speaker is additionally flagged for mandatory external/human review (attribution
# is the human gate). verify_quotes() is deterministic and offline; it powers both
# the claim audit's quote_verification field and the QA fake_quote_risk check.

QUOTE_MATCH_THRESHOLD = 0.9
_MIN_GATED_QUOTE_CHARS = 10

_STRAIGHT_QUOTE_RE = re.compile(r'"([^"\n]{1,400})"')
_CURLY_QUOTE_RE = re.compile("[“]([^”\n]{1,400})[”]")


def extract_quotes(text: str) -> list[tuple[int, str]]:
    """Return (position, inner_text) for every straight or curly quoted span."""
    spans: list[tuple[int, str]] = []
    for match in _STRAIGHT_QUOTE_RE.finditer(text or ""):
        spans.append((match.start(), match.group(1)))
    for match in _CURLY_QUOTE_RE.finditer(text or ""):
        spans.append((match.start(), match.group(1)))
    spans.sort(key=lambda item: item[0])
    return spans


def _normalize_for_match(text: str) -> str:
    lowered = (text or "").lower()
    lowered = (
        lowered.replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
    )
    lowered = re.sub(r"[^a-z0-9' ]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _best_match_ratio(quote_norm: str, transcript_norm: str) -> float:
    """Best local similarity of a normalized quote against a normalized transcript.

    Fast path: exact containment -> 1.0. Otherwise slide a window the size of the
    quote across the transcript and take the max SequenceMatcher ratio, which
    tolerates minor ASR / punctuation drift without being diluted by transcript
    length.
    """
    if not quote_norm or not transcript_norm:
        return 0.0
    if quote_norm in transcript_norm:
        return 1.0
    length = len(quote_norm)
    window = max(length + 12, int(length * 1.3))
    step = max(1, length // 4)
    matcher = difflib.SequenceMatcher(autojunk=False)
    matcher.set_seq1(quote_norm)
    best = 0.0
    for start in range(0, max(1, len(transcript_norm) - length + 1), step):
        matcher.set_seq2(transcript_norm[start : start + window])
        ratio = matcher.ratio()
        if ratio > best:
            best = ratio
            if best >= 0.995:
                break
    return best


def _person_names(packet: dict[str, Any], team_slugs: tuple[str, ...] = ("mystics",)) -> dict[str, str]:
    """Map name token (lowercased full name or surname, len>=4) -> canonical full name.

    Includes roster players AND coaching staff, since coaches speak at pressers.
    """
    mapping: dict[str, str] = {}

    def add(full: Any) -> None:
        name = str(full or "").strip()
        if not name:
            return
        mapping.setdefault(name.lower(), name)
        for part in re.split(r"\s+", name):
            if len(part) >= 4 and re.fullmatch(r"[A-Za-z'-]+", part):
                mapping.setdefault(part.lower(), name)

    for slug in team_slugs:
        path = PROJECT_ROOT / "data" / "teams" / f"{slug}.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for player in data.get("roster") or []:
            add(player.get("name"))
        add((data.get("head_coach") or {}).get("name"))
        for coach in data.get("coaching_staff") or []:
            add(coach.get("name"))
    return mapping


def _quote_speaker(body: str, pos: int, raw_len: int, names: dict[str, str]) -> str | None:
    """Best-effort: return a canonical name if one appears near the quote."""
    window = body[max(0, pos - 90) : pos + raw_len + 90].lower()
    for token, full in names.items():
        if re.search(rf"\b{re.escape(token)}\b", window):
            return full
    return None


def _segment_link(video_id: str, start: Any) -> dict[str, Any]:
    """Timestamp (mm:ss) + clickable deep link to the moment in the source video.
    For editor review only; these never go into the published article body."""
    seconds = int(float(start or 0))
    minutes, secs = divmod(seconds, 60)
    return {
        "start_seconds": seconds,
        "timestamp": f"{minutes:02d}:{secs:02d}",
        "source_link": f"https://www.youtube.com/watch?v={video_id}&t={seconds}s",
    }


def _match_quote_segments(
    quote_text: str, video_norm: list[dict[str, Any]], matched_video_id: str | None
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Return (video, segment) pairs from the matched video whose corrected text
    overlaps the quote."""
    qn = _normalize_for_match(quote_text)
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for video in video_norm:
        if matched_video_id and video["video_id"] != matched_video_id:
            continue
        for segment in video["segments"]:
            seg_norm = _normalize_for_match(str(segment.get("text") or ""))
            if not seg_norm:
                continue
            if seg_norm in qn or qn in seg_norm or _best_match_ratio(seg_norm, qn) >= 0.8:
                pairs.append((video, segment))
    return pairs


def _used_segments(quotes_out: list[dict[str, Any]], video_norm: list[dict[str, Any]]) -> list[dict[str, Any]]:
    used: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for quote in quotes_out:
        if not quote.get("verified"):
            continue
        for video, segment in _match_quote_segments(quote["text"], video_norm, quote.get("matched_video_id")):
            key = (video["video_id"], segment.get("start"), segment.get("text"))
            if key in seen:
                continue
            seen.add(key)
            entry = {
                "video_id": video["video_id"],
                "kind": video["kind"],
                "start": segment.get("start"),
                "duration": segment.get("duration"),
                "text": segment.get("text"),
            }
            entry.update(_segment_link(video["video_id"], segment.get("start")))
            used.append(entry)
    return used


def verify_quotes(body: str, packet: dict[str, Any], *, threshold: float = QUOTE_MATCH_THRESHOLD) -> dict[str, Any]:
    """Verify every quoted span in ``body`` against the packet's CORRECTED transcripts.

    A quoted, multi-word span (>= _MIN_GATED_QUOTE_CHARS) that does not match any
    transcript region at >= ``threshold`` is an unverified quote and sets
    ``hard_fail`` True. Quotes that name a known speaker set
    ``requires_external_review``. Raw transcript text is preserved on the packet;
    matching uses the corrected text per Stage B's rule.
    """
    transcripts = [
        t
        for t in (packet.get("media_transcripts") or [])
        if isinstance(t, dict) and t.get("status") == "ok"
    ]
    video_norm = [
        {
            "video_id": str(t.get("video_id") or ""),
            "kind": str(t.get("kind") or ""),
            "norm": _normalize_for_match(t.get("corrected_text") or t.get("text") or ""),
            "segments": t.get("corrected_segments") or t.get("segments") or [],
        }
        for t in transcripts
    ]
    names = _person_names(packet)

    quotes_out: list[dict[str, Any]] = []
    for pos, raw in extract_quotes(body):
        span = raw.strip()
        gated = len(span) >= _MIN_GATED_QUOTE_CHARS and " " in span
        quote_norm = _normalize_for_match(span)
        best_ratio, best_vid, best_kind = 0.0, None, None
        for video in video_norm:
            ratio = _best_match_ratio(quote_norm, video["norm"])
            if ratio > best_ratio:
                best_ratio, best_vid, best_kind = ratio, video["video_id"], video["kind"]
        verified = bool(quote_norm) and best_ratio >= threshold
        speaker = _quote_speaker(body, pos, len(raw), names)
        quote = {
            "text": span,
            "match_ratio": round(best_ratio, 3),
            "verified": verified,
            "gated": gated,
            "matched_video_id": best_vid if verified else None,
            "matched_kind": best_kind if verified else None,
            "attributed": speaker is not None,
            "speaker": speaker,
            "requires_external_review": speaker is not None,
        }
        # Attach the transcript timestamp + deep link for verified quotes (review only).
        if verified and best_vid:
            pairs = _match_quote_segments(span, video_norm, best_vid)
            if pairs:
                earliest = min(pairs, key=lambda pair: float(pair[1].get("start") or 0))
                quote.update(_segment_link(best_vid, earliest[1].get("start")))
        quotes_out.append(quote)

    unverified = [q for q in quotes_out if q["gated"] and not q["verified"]]
    attributed = [q for q in quotes_out if q["attributed"]]
    return {
        "checked": len(quotes_out),
        "gated_count": sum(1 for q in quotes_out if q["gated"]),
        "verified_count": sum(1 for q in quotes_out if q["verified"]),
        "unverified_count": len(unverified),
        "threshold": threshold,
        "hard_fail": bool(unverified),
        "requires_external_review": bool(attributed),
        "quotes": quotes_out,
        "unverified_quotes": unverified,
        "attributed_quotes": attributed,
        "used_segments": _used_segments(quotes_out, video_norm),
    }


# ── Roster / coach name-validation gate (Stage B) ─────────────────────────────
#
# After the 2026-05-29 live run wrote "Coach Cindy Johnson" (the Mystics coach is
# Sydney Johnson), this gate checks person names presented in the body against the
# known roster + coaching staff of BOTH teams (team KBs + the game's box-score
# names). Unknown names are flagged for external review; a clearly wrong
# head-coach name hard-fails (-> deterministic fallback in the orchestrator).

# Capitalized name tokens only; case-sensitive name groups (no re.IGNORECASE).
_COACH_NAME_RE = re.compile(r"\b(?:[Hh]ead\s+[Cc]oach|[Cc]oach)\s+([A-Z][A-Za-z.'-]+)\s+([A-Z][A-Za-z.'-]+)")
_SPEAKER_NAME_RE = re.compile(
    r"\b([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,2})\s+(?:said|added|told|noted|explained|continued)\b"
)
_NON_PERSON_TOKENS = {
    "the", "a", "an", "coach", "head", "seattle", "washington", "mystics", "storm", "sparks",
    "dallas", "wings", "los", "angeles", "indiana", "fever", "new", "york", "liberty", "chicago",
    "sky", "atlanta", "dream", "climate", "pledge", "arena", "center", "carefirst", "first",
    "second", "third", "fourth", "quarter", "half", "game", "storm's", "january", "february",
    "march", "april", "may", "june", "july", "august", "september", "october", "november",
    "december", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
}


def _slugify_team(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")


def _known_persons(packet: dict[str, Any], team_slugs: tuple[str, ...] = ("mystics",)):
    """Build the known-person set from team KBs (both teams) + the game box scores.

    Returns (token_map, full_set, head_coaches) where token_map maps a lowercased
    name token (first or last, len>=3) to the set of full names that contain it,
    full_set is lowercased full names, and head_coaches lists {first,last,full}.
    """
    token_map: dict[str, set[str]] = {}
    full_set: set[str] = set()
    head_coaches: list[dict[str, str]] = []

    def add_person(full: Any) -> None:
        name = str(full or "").strip()
        if not name:
            return
        full_set.add(name.lower())
        for part in re.split(r"\s+", name):
            token = part.strip(".,'").lower()
            if len(token) >= 3 and re.fullmatch(r"[a-z'-]+", token):
                token_map.setdefault(token, set()).add(name)

    slugs = list(team_slugs)
    opponent = _opponent_team((packet.get("game") or {}).get("teams") or [])
    opp_slug = _slugify_team(opponent.get("name") or "")
    if opp_slug and opp_slug not in slugs:
        slugs.append(opp_slug)

    for slug in slugs:
        path = PROJECT_ROOT / "data" / "teams" / f"{slug}.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for player in data.get("roster") or []:
            add_person(player.get("name"))
        head_coach = (data.get("head_coach") or {}).get("name")
        if head_coach:
            add_person(head_coach)
            parts = [p for p in re.split(r"\s+", str(head_coach).strip()) if p]
            if len(parts) >= 2:
                head_coaches.append({"first": parts[0].lower(), "last": parts[-1].lower(), "full": head_coach})
        for coach in data.get("coaching_staff") or []:
            add_person(coach.get("name"))

    # The game's ESPN box-score names are verified persons for THIS game (covers
    # opponent players when no opponent KB file exists).
    for team in (packet.get("game") or {}).get("teams") or []:
        for row in team.get("box_score") or []:
            add_person(row.get("player"))
    for performer in (packet.get("narrative") or {}).get("top_performers") or []:
        add_person(performer.get("player"))

    return token_map, full_set, head_coaches


def validate_person_names(packet: dict[str, Any], body: str) -> dict[str, Any]:
    """Flag person names in the body that match no known roster/coaching-staff person.

    - Coach-context names hard-fail when the head-coach name is clearly wrong
      (right surname, wrong first name) or matches no known person at all.
    - Speaker-context names ("X said") that match no known person are flagged for
      external review (advisory), since an invented speaker is a fabrication risk.
    """
    token_map, full_set, head_coaches = _known_persons(packet)
    flagged: list[dict[str, str]] = []
    hard_fail = False

    def token_known(token: str) -> bool:
        return token.strip(".,'").lower() in token_map

    for match in _COACH_NAME_RE.finditer(body or ""):
        first, last = match.group(1), match.group(2)
        full = f"{first} {last}"
        fl, ll = first.lower(), last.lower()
        wrong_head_coach = any(hc["last"] == ll and hc["first"] != fl for hc in head_coaches)
        is_known = full.lower() in full_set or token_known(first) or token_known(last)
        if wrong_head_coach:
            flagged.append({
                "name": full,
                "context": "head_coach",
                "severity": "hard_fail",
                "reason": "head-coach name does not match the known coach: "
                          + ", ".join(hc["full"] for hc in head_coaches),
            })
            hard_fail = True
        elif not is_known:
            flagged.append({
                "name": full,
                "context": "head_coach",
                "severity": "hard_fail",
                "reason": "coach name matches no known roster or coaching-staff person",
            })
            hard_fail = True

    flagged_names_lower = {f["name"].lower() for f in flagged}
    for match in _SPEAKER_NAME_RE.finditer(body or ""):
        candidate = match.group(1).strip()
        tokens = [t for t in re.split(r"\s+", candidate) if t]
        if not tokens or tokens[0].lower() in _NON_PERSON_TOKENS:
            continue
        is_known = candidate.lower() in full_set or any(token_known(t) for t in tokens)
        if not is_known and candidate.lower() not in flagged_names_lower:
            flagged_names_lower.add(candidate.lower())
            flagged.append({
                "name": candidate,
                "context": "speaker",
                "severity": "review",
                "reason": "attributed speaker matches no known roster or coaching-staff person",
            })

    return {
        "known_person_count": len(full_set),
        "flagged_names": flagged,
        "hard_fail": hard_fail,
        "requires_external_review": bool(flagged),
    }
