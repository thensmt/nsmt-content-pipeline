"""Advisory editorial QA scoring for Mystics recap outputs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ingestion.cache import iso_utc
from newsroom.common import DEFAULT_QA_DIR, _dedupe_strings, _display_path, _load_assets_from_paths, _opponent_team, _selected_angle, _word_count
from newsroom.drafts import render_markdown_draft
from newsroom.schemas import validate_qa_report

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
]

def format_editorial_qa_report(
    packet: dict[str, Any],
    *,
    article_markdown: str | None = None,
    article_markdown_path: Path | str | None = None,
    packet_path: Path | str | None = None,
    assets: dict[str, Any] | None = None,
    asset_paths: dict[str, Path | str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build an advisory editorial QA report for generated local outputs."""
    if article_markdown is None and article_markdown_path and Path(article_markdown_path).exists():
        article_markdown = Path(article_markdown_path).read_text()
    article_markdown = article_markdown or render_markdown_draft(packet)

    asset_paths = asset_paths or {}
    if assets is None and asset_paths:
        assets = _load_assets_from_paths(asset_paths)
    assets = assets or {}

    item_reports: dict[str, Any] = {
        "main_article": _qa_item_report(
            packet,
            "main_article",
            article_markdown,
            path=article_markdown_path,
        )
    }
    for item_key in (
        "short_recap",
        "takeaways",
        "push_alert",
        "newsletter_blurb",
        "seo_summary",
        "social_caption",
        "headline_candidates",
    ):
        if item_key in assets:
            item_reports[item_key] = _qa_item_report(
                packet,
                item_key,
                assets[item_key],
                path=asset_paths.get(item_key),
            )

    summary = _qa_report_summary(item_reports)
    selected = _selected_angle(packet)
    report = {
        "schema_version": "mystics-editorial-qa/v0.1",
        "event_id": packet["game"]["id"],
        "generation_timestamp": generated_at or iso_utc(),
        "score_scale": "0-100, where 100 means strongest editorial readiness; risk categories score lower when risk is higher.",
        "score_categories": list(QA_SCORE_CATEGORIES),
        "supported_issue_flags": list(QA_ISSUE_FLAGS),
        "selected_story_angle": selected,
        "article_markdown_path": _display_path(article_markdown_path) if article_markdown_path else None,
        "packet_path": _display_path(packet_path) if packet_path else None,
        "asset_paths": {key: _display_path(path) for key, path in sorted(asset_paths.items())},
        "item_reports": item_reports,
        "summary": summary,
        "overall_recommendation": summary["overall_recommendation"],
        "advisory_only": True,
    }
    return validate_qa_report(report)


def write_editorial_qa_report(
    packet: dict[str, Any],
    *,
    article_markdown_path: Path | str,
    packet_path: Path | str,
    qa_dir: Path = DEFAULT_QA_DIR,
    assets: dict[str, Any] | None = None,
    asset_paths: dict[str, Path | str] | None = None,
    generated_at: str | None = None,
) -> Path:
    """Write an advisory editorial QA JSON report. This does not publish."""
    qa_dir.mkdir(parents=True, exist_ok=True)
    event_id = packet["game"]["id"]
    report_path = qa_dir / f"mystics-qa-{event_id}.json"
    report = format_editorial_qa_report(
        packet,
        article_markdown_path=article_markdown_path,
        packet_path=packet_path,
        assets=assets,
        asset_paths=asset_paths,
        generated_at=generated_at,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report_path


def _qa_item_report(
    packet: dict[str, Any],
    item_key: str,
    content: Any,
    *,
    path: Path | str | None = None,
) -> dict[str, Any]:
    text = _qa_item_text(item_key, content)
    issue_flags = _qa_issue_flags(packet, item_key, content, text)
    scores = _qa_scores(item_key, text, issue_flags)
    report = {
        "item_key": item_key,
        "label": _qa_item_label(item_key),
        "path": _display_path(path) if path else None,
        "word_count": _qa_word_count_for_item(item_key, content, text),
        "character_count": len(text),
        "issue_flags": issue_flags,
        "scores": scores,
        "overall_score": int(round(sum(scores.values()) / len(scores))),
        "notes": _qa_notes(item_key, issue_flags),
    }
    return report


def _qa_item_label(item_key: str) -> str:
    labels = {
        "main_article": "Main article draft",
        "short_recap": "Short recap",
        "takeaways": "3 takeaways",
        "push_alert": "Push alert",
        "newsletter_blurb": "Newsletter blurb",
        "seo_summary": "SEO summary",
        "social_caption": "Social caption",
        "headline_candidates": "Headline candidates",
    }
    return labels.get(item_key, item_key.replace("_", " ").title())


def _qa_item_text(item_key: str, content: Any) -> str:
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


def _qa_issue_flags(packet: dict[str, Any], item_key: str, content: Any, text: str) -> list[str]:
    flags: list[str] = []
    if _qa_requires_score(item_key) and not _qa_contains_score(packet, text):
        flags.append("missing_score")
    if _qa_requires_opponent(item_key) and not _qa_contains_opponent(packet, text):
        flags.append("missing_opponent")
    if _qa_requires_top_performers(item_key) and not _qa_contains_top_performer(packet, text):
        flags.append("missing_top_performers")
    if _qa_has_unsupported_causality(text):
        flags.append("unsupported_causality")
    if _qa_has_fake_quote_risk(packet, text):
        flags.append("fake_quote_risk")
    if _qa_is_too_generic(item_key, text):
        flags.append("too_generic")
    if _qa_is_clickbaity(text):
        flags.append("too_clickbaity")
    flags.extend(_qa_length_issue_flags(item_key, content, text))
    if item_key == "headline_candidates" and _qa_headline_candidates_weak(content):
        flags.append("headline_weak")
    if item_key == "social_caption" and _qa_social_caption_weak(packet, text):
        flags.append("social_caption_weak")
    if _qa_has_memory_overreach(text):
        flags.append("memory_overreach")
    return [flag for flag in _dedupe_strings(flags) if flag in QA_ISSUE_FLAGS]


def _qa_scores(item_key: str, text: str, issue_flags: list[str]) -> dict[str, int]:
    penalties = {
        "missing_score": {
            "factual_safety": 16,
            "source_support": 24,
            "clarity": 8,
            "publish_readiness": 18,
        },
        "missing_opponent": {
            "factual_safety": 10,
            "source_support": 16,
            "clarity": 12,
            "publish_readiness": 14,
        },
        "missing_top_performers": {
            "source_support": 12,
            "clarity": 8,
            "publish_readiness": 10,
        },
        "unsupported_causality": {
            "factual_safety": 28,
            "source_support": 18,
            "unsupported_claim_risk": 30,
            "publish_readiness": 26,
        },
        "fake_quote_risk": {
            "factual_safety": 40,
            "source_support": 30,
            "unsupported_claim_risk": 38,
            "publish_readiness": 35,
        },
        "too_generic": {
            "clarity": 18,
            "nsmt_voice_fit": 18,
            "source_support": 8,
            "publish_readiness": 14,
        },
        "too_clickbaity": {
            "factual_safety": 10,
            "clarity": 12,
            "nsmt_voice_fit": 24,
            "publish_readiness": 18,
        },
        "too_long": {
            "clarity": 16,
            "nsmt_voice_fit": 8,
            "publish_readiness": 12,
        },
        "too_short": {
            "clarity": 14,
            "source_support": 12,
            "publish_readiness": 12,
        },
        "headline_weak": {
            "clarity": 10,
            "nsmt_voice_fit": 8,
            "publish_readiness": 8,
        },
        "social_caption_weak": {
            "clarity": 12,
            "nsmt_voice_fit": 12,
            "publish_readiness": 10,
        },
        "memory_overreach": {
            "factual_safety": 18,
            "source_support": 16,
            "unsupported_claim_risk": 22,
            "publish_readiness": 18,
        },
    }
    scores = {
        "factual_safety": 94,
        "source_support": 92,
        "clarity": 90,
        "nsmt_voice_fit": 88,
        "repetition_risk": _qa_repetition_score(text),
        "unsupported_claim_risk": 92,
        "publish_readiness": 88,
    }
    if item_key == "main_article":
        scores["nsmt_voice_fit"] += 2
    for flag in issue_flags:
        for category, penalty in penalties.get(flag, {}).items():
            scores[category] = scores.get(category, 90) - penalty
        if flag in {"too_generic", "too_long"}:
            scores["repetition_risk"] -= 5
    return {category: _clamp_score(scores[category]) for category in QA_SCORE_CATEGORIES}


def _qa_notes(item_key: str, issue_flags: list[str]) -> list[str]:
    if not issue_flags:
        return [f"{_qa_item_label(item_key)} is ready for normal human review."]
    return [f"Review {flag.replace('_', ' ')} before editor handoff." for flag in issue_flags]


def _qa_report_summary(item_reports: dict[str, Any]) -> dict[str, Any]:
    lowest = sorted(item_reports.values(), key=lambda item: (item["overall_score"], item["scores"]["publish_readiness"]))
    lowest_scoring_items = [
        {
            "item_key": item["item_key"],
            "label": item["label"],
            "overall_score": item["overall_score"],
            "publish_readiness": item["scores"]["publish_readiness"],
            "issue_flags": item["issue_flags"],
        }
        for item in lowest[:3]
    ]
    issue_counts: dict[str, int] = {}
    for item in item_reports.values():
        for flag in item.get("issue_flags") or []:
            issue_counts[flag] = issue_counts.get(flag, 0) + 1
    top_issue_flags = [
        {"flag": flag, "count": count}
        for flag, count in sorted(issue_counts.items(), key=lambda row: (-row[1], row[0]))[:5]
    ]

    lowest_publish = min((item["scores"]["publish_readiness"] for item in item_reports.values()), default=0)
    lowest_overall = min((item["overall_score"] for item in item_reports.values()), default=0)
    severe_flags = {"fake_quote_risk", "unsupported_causality", "memory_overreach"}
    has_severe = any(flag in severe_flags for flag in issue_counts)
    blocking_flags = set(issue_counts) - {"headline_weak"}
    if lowest_publish < 50 or lowest_overall < 58 or has_severe:
        recommendation = "reject_and_regenerate"
    elif lowest_publish < 74 or blocking_flags:
        recommendation = "needs_human_revision"
    else:
        recommendation = "approve_for_editor_review"

    return {
        "overall_recommendation": recommendation,
        "lowest_scoring_items": lowest_scoring_items,
        "top_issue_flags": top_issue_flags,
        "item_count": len(item_reports),
    }


def _qa_requires_score(item_key: str) -> bool:
    return item_key in {"main_article", "short_recap", "push_alert", "newsletter_blurb", "seo_summary", "social_caption"}


def _qa_requires_opponent(item_key: str) -> bool:
    return item_key in {
        "main_article",
        "short_recap",
        "push_alert",
        "newsletter_blurb",
        "seo_summary",
        "social_caption",
        "headline_candidates",
    }


def _qa_requires_top_performers(item_key: str) -> bool:
    return item_key in {"main_article", "short_recap", "takeaways", "newsletter_blurb"}


def _qa_contains_score(packet: dict[str, Any], text: str) -> bool:
    lower = text.lower()
    final_score = str((packet.get("narrative") or {}).get("final_score") or "").lower()
    if final_score and final_score in lower:
        return True
    teams = ((packet.get("game") or {}).get("teams") or [])
    if len(teams) >= 2:
        scores = [str(team.get("score")) for team in teams if team.get("score") is not None]
        if len(scores) >= 2 and all(score in lower for score in scores[:2]):
            return True
    return False


def _qa_contains_opponent(packet: dict[str, Any], text: str) -> bool:
    lower = text.lower()
    try:
        opponent = _opponent_team(packet["game"]["teams"])
    except (KeyError, ValueError):
        return False
    names = {
        opponent.get("name", ""),
        opponent.get("abbreviation", ""),
        str(opponent.get("name", "")).replace("Washington ", ""),
    }
    return any(name and name.lower() in lower for name in names)


def _qa_contains_top_performer(packet: dict[str, Any], text: str) -> bool:
    lower = text.lower()
    performers = (packet.get("narrative") or {}).get("top_performers") or []
    names = [str(performer.get("player") or "") for performer in performers[:6]]
    return bool(names) and any(name and name.lower() in lower for name in names)


def _qa_has_unsupported_causality(text: str) -> bool:
    lower = text.lower()
    markers = [
        "wanted it more",
        "did not care",
        "didn't care",
        "sent a message",
        "proved that",
        "proves that",
        "showed who they are",
        "because of effort",
        "coach decided",
        "locker room",
        "huddle",
        "halftime speech",
        "guarantees",
        "will carry over",
    ]
    for marker in markers:
        index = lower.find(marker)
        if index == -1:
            continue
        window = lower[max(0, index - 36) : index + len(marker) + 36]
        if any(safe_context in window for safe_context in ("do not", "avoid", "without", "not add")):
            continue
        return True
    return False


def _qa_has_fake_quote_risk(packet: dict[str, Any], text: str) -> bool:
    # When transcripts are attached, defer to the hard verifier: flag only when a
    # quoted span cannot be matched to the corrected transcript. This keeps QA from
    # nonsensically flagging legitimate verified presser quotes as fake.
    if packet.get("media_transcripts"):
        from newsroom.claim_audit import verify_quotes

        # Verify the reader body only: strip YAML frontmatter (json.dumps wraps
        # title/score values in quotes that are not transcript quotes) and the
        # trailing editorial sections after the excerpt marker.
        body = re.sub(r"^\s*---.*?---\s*", "", text, flags=re.DOTALL)
        if "**Excerpt:**" in body:
            body = body.split("**Excerpt:**", 1)[0]
        return verify_quotes(body, packet)["unverified_count"] > 0
    lower = text.lower()
    if any(marker in lower for marker in ("told reporters", "said after", "said postgame", "quote from")):
        return True
    quote_like = re.search(r"[\"“][^\"”]{8,}[\"”]", text)
    quote_verbs = re.search(r"\b(said|told)\b", lower)
    return bool(quote_like and quote_verbs)


def _qa_is_too_generic(item_key: str, text: str) -> bool:
    lower = text.lower()
    generic_markers = [
        "good game",
        "big game",
        "things happened",
        "did stuff",
        "played hard",
        "need to do better",
        "full article explains everything",
    ]
    if any(marker in lower for marker in generic_markers):
        return True
    return item_key != "push_alert" and _word_count(text) < 10


def _qa_is_clickbaity(text: str) -> bool:
    lower = text.lower()
    markers = [
        "you won't believe",
        "shocking",
        "must-see",
        "insane",
        "destroyed",
        "humiliated",
        "disaster",
        "meltdown",
    ]
    return any(marker in lower for marker in markers)


def _qa_length_issue_flags(item_key: str, content: Any, text: str) -> list[str]:
    flags: list[str] = []
    words = _qa_word_count_for_item(item_key, content, text)
    if item_key == "main_article":
        if words > 820:
            flags.append("too_long")
        elif words < 580:
            flags.append("too_short")
    elif item_key == "short_recap":
        if words > 180:
            flags.append("too_long")
        elif words < 120:
            flags.append("too_short")
    elif item_key == "takeaways":
        count = _qa_takeaway_count(content, text)
        if count > 3:
            flags.append("too_long")
        elif count < 3:
            flags.append("too_short")
    elif item_key == "push_alert":
        if len(text) > 160:
            flags.append("too_long")
        elif len(text.strip()) < 45:
            flags.append("too_short")
    elif item_key == "newsletter_blurb":
        if words > 120:
            flags.append("too_long")
        elif words < 75:
            flags.append("too_short")
    elif item_key == "seo_summary":
        if words > 100:
            flags.append("too_long")
        elif words < 35:
            flags.append("too_short")
    elif item_key == "social_caption":
        if len(text) > 280:
            flags.append("too_long")
        elif len(text.strip()) < 50:
            flags.append("too_short")
    elif item_key == "headline_candidates":
        count = _qa_headline_count(content, text)
        if count > 5:
            flags.append("too_long")
        elif count < 5:
            flags.append("too_short")
    return flags


def _qa_word_count_for_item(item_key: str, content: Any, text: str) -> int:
    if item_key == "main_article":
        return _word_count(_qa_article_core_text(text))
    return _word_count(text)


def _qa_article_core_text(markdown: str) -> str:
    body = markdown.split("**Excerpt:**", 1)[0]
    if "**By " in body:
        body = body.split("**By ", 1)[-1]
        body = body.split("**", 1)[-1]
    return body


def _qa_takeaway_count(content: Any, text: str) -> int:
    if isinstance(content, list):
        return len(content)
    return len([line for line in text.splitlines() if line.strip().startswith("- ")])


def _qa_headline_count(content: Any, text: str) -> int:
    if isinstance(content, list):
        return len(content)
    return len([line for line in text.splitlines() if line.strip()])


def _qa_headline_candidates_weak(content: Any) -> bool:
    if not isinstance(content, list) or len(content) != 5:
        return True
    headlines = [str(item.get("headline") or "") for item in content if isinstance(item, dict)]
    if len(headlines) != 5:
        return True
    weak_starts = ("what the box score says", "mystics update", "game recap")
    return any(len(headline) < 30 or headline.lower().startswith(weak_starts) for headline in headlines)


def _qa_social_caption_weak(packet: dict[str, Any], text: str) -> bool:
    hashtag_count = text.count("#")
    return hashtag_count > 2 or not _qa_contains_score(packet, text) or len(text.strip()) < 50


def _qa_has_memory_overreach(text: str) -> bool:
    lower = text.lower()
    markers = [
        "season-long trend",
        "defines their identity",
        "team culture",
        "always",
        "never",
        "signature flaw",
        "franchise-changing",
    ]
    return any(marker in lower for marker in markers)


def _qa_repetition_score(text: str) -> int:
    words = [
        word.lower()
        for word in re.findall(r"\b[\w'-]+\b", text)
        if len(word) > 3 and word.lower() not in {"washington", "mystics", "dallas", "wings", "game", "score"}
    ]
    if len(words) < 40:
        return 88
    counts: dict[str, int] = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    repeated_terms = sum(1 for count in counts.values() if count >= 5)
    return _clamp_score(92 - min(28, repeated_terms * 4))


def _clamp_score(value: Any) -> int:
    return int(max(0, min(100, round(float(value)))))
