"""Normalize ESPN Mystics payloads into local postgame packets."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ingestion.cache import iso_utc
from ingestion.espn_mystics import SCHEDULE_URL_TMPL, SUMMARY_URL_TMPL, _event_date, _event_from_fixture_scoreboards, _status
from newsroom.common import DEFAULT_MEMORY_DIR, LEAGUE, TEAM_ABBR, TEAM_ID, TEAM_NAME, _load_writer_profile, _to_int
from newsroom.memory import load_mystics_memory
from newsroom.schemas import validate_normalized_game_packet
from newsroom.story_angles import extract_narrative_signals, select_story_angles

def build_postgame_packet(
    payloads: dict[str, Any],
    *,
    retrieved_at: str | None = None,
    memory_dir: Path | str | None = DEFAULT_MEMORY_DIR,
    include_transcripts: bool | None = None,
    transcript_videos: list[Any] | None = None,
    transcript_team_slugs: tuple[str, ...] = ("mystics",),
    transcript_name_tokens: dict[str, str] | None = None,
    transcript_fetcher: Any = None,
) -> dict[str, Any]:
    """Normalize ESPN payloads and add narrative signals.

    Transcript enrichment (Mac-side / residential IP only) is OFF by default, so
    the deterministic path is unaffected. It turns on when ``include_transcripts``
    is True, or when ``include_transcripts`` is None and the
    ``NSMT_INCLUDE_TRANSCRIPTS`` env var is truthy. When on, ``transcript_videos``
    (``[{"video_id", "kind"}, ...]``) is a manual override that bypasses channel
    discovery; if omitted, discovery is attempted for the game's two teams. Any
    network fetch happens only when transcripts are enabled.
    """
    retrieved = retrieved_at or payloads.get("retrieved_at") or iso_utc()
    event = payloads.get("event") or _event_from_fixture_scoreboards(payloads)
    if not isinstance(event, dict):
        raise ValueError("ESPN payloads must include a completed Mystics event")
    summary = payloads.get("summary") or {}
    schedule = payloads.get("schedule") or {}
    writer_profile = _load_writer_profile()

    normalized = _normalize_game(event, summary, schedule, payloads, retrieved)
    normalized["memory"] = load_mystics_memory(memory_dir)
    narrative = extract_narrative_signals(normalized)
    normalized["narrative"] = narrative
    normalized["story_angles"] = select_story_angles(normalized)
    normalized["writer_profile"] = writer_profile

    if _transcripts_enabled(include_transcripts):
        _attach_transcripts(
            normalized,
            transcript_videos=transcript_videos,
            team_slugs=transcript_team_slugs,
            name_tokens=transcript_name_tokens,
            fetcher=transcript_fetcher,
            retrieved_at=retrieved,
        )

    return validate_normalized_game_packet(normalized)


def _transcripts_enabled(include_transcripts: bool | None) -> bool:
    if include_transcripts is not None:
        return bool(include_transcripts)
    return os.environ.get("NSMT_INCLUDE_TRANSCRIPTS", "").strip().lower() in ("1", "true", "yes", "on")


def enrich_packet_with_transcripts(
    packet: dict[str, Any],
    *,
    transcript_videos: list[Any] | None = None,
    team_slugs: tuple[str, ...] = ("mystics",),
    name_tokens: dict[str, str] | None = None,
    fetcher: Any = None,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Attach (or refresh) ``media_transcripts`` on an already-built packet, then
    re-validate. Manual-override entry point: pass
    ``transcript_videos=[{"video_id", "kind"}, ...]``."""
    retrieved = retrieved_at or packet.get("retrieved_at") or iso_utc()
    _attach_transcripts(
        packet,
        transcript_videos=transcript_videos,
        team_slugs=team_slugs,
        name_tokens=name_tokens,
        fetcher=fetcher,
        retrieved_at=retrieved,
    )
    return validate_normalized_game_packet(packet)


def _attach_transcripts(
    normalized: dict[str, Any],
    *,
    transcript_videos: list[Any] | None,
    team_slugs: tuple[str, ...],
    name_tokens: dict[str, str] | None,
    fetcher: Any,
    retrieved_at: str,
) -> None:
    """Fetch + name-correct transcripts and attach ``media_transcripts`` + sources.

    Local import keeps the deterministic path free of the transcript dependency.
    """
    from ingestion.fetchers.youtube_transcripts import build_media_transcripts, discover_game_videos

    videos = transcript_videos
    if videos is None:
        # No manual override: best-effort discovery for the two teams in this game.
        teams = [team.get("name") for team in normalized.get("game", {}).get("teams", []) if team.get("name")]
        try:
            videos = discover_game_videos(normalized.get("game", {}).get("date", ""), teams)
        except Exception:  # discovery is best-effort; never block packet assembly
            videos = []

    media = build_media_transcripts(
        videos,
        name_tokens=name_tokens,
        team_slugs=team_slugs,
        retrieved_at=retrieved_at,
        fetcher=fetcher,
    )
    normalized["media_transcripts"] = media

    sources = normalized.setdefault("sources", [])
    existing_urls = {src.get("url") for src in sources if isinstance(src, dict)}
    for item in media:
        url = item.get("source_url", "")
        if url and url in existing_urls:
            continue
        existing_urls.add(url)
        sources.append(
            {
                "name": f"YouTube {item.get('kind', 'video')} transcript ({item.get('video_id', '')})",
                "url": url,
                "retrieved_at": item.get("retrieved_at", retrieved_at),
            }
        )


def _normalize_game(
    event: dict[str, Any],
    summary: dict[str, Any],
    schedule: dict[str, Any],
    payloads: dict[str, Any],
    retrieved_at: str,
) -> dict[str, Any]:
    competition = (event.get("competitions") or [{}])[0]
    teams = [_normalize_team(comp, summary) for comp in competition.get("competitors", [])]
    teams.sort(key=lambda item: 0 if item.get("home_away") == "away" else 1)
    game_id = str(event.get("id") or competition.get("id") or "")
    game_date = _event_date(event)

    return {
        "schema_version": "mystics-postgame-recap/v0.2",
        "retrieved_at": retrieved_at,
        "team": {
            "id": TEAM_ID,
            "name": TEAM_NAME,
            "abbreviation": TEAM_ABBR,
            "league": LEAGUE,
        },
        "schedule": _schedule_context(schedule, game_id, payloads.get("as_of")),
        "game": {
            "id": game_id,
            "date": game_date,
            "name": event.get("name") or "",
            "short_name": event.get("shortName") or "",
            "season": (event.get("season") or {}).get("year") or payloads.get("season"),
            "season_type": (event.get("season") or {}).get("slug")
            or (event.get("seasonType") or {}).get("name")
            or "",
            "venue": (competition.get("venue") or {}).get("fullName") or "",
            "attendance": competition.get("attendance") or (summary.get("gameInfo") or {}).get("attendance"),
            "neutral_site": bool(competition.get("neutralSite", False)),
            "status": _status(event),
            "teams": teams,
            "scoring_by_quarter": _scoring_by_quarter(teams),
            "leaders": _leaders(summary, teams),
            "play_by_play": _play_by_play(summary),
            "gamecast": _gamecast(summary),
        },
        "sources": _sources(payloads, game_id, game_date, retrieved_at),
    }


def _normalize_team(competitor: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    team = competitor.get("team") or {}
    team_id = str(team.get("id") or competitor.get("id") or "")
    name = team.get("displayName") or ""
    return {
        "id": team_id,
        "name": name,
        "abbreviation": team.get("abbreviation") or "",
        "home_away": competitor.get("homeAway") or "",
        "score": _to_int(competitor.get("score")),
        "winner": bool(competitor.get("winner")),
        "line_score": _line_score(competitor),
        "team_stats": _team_stats(summary, team_id, name),
        "box_score": _box_score(summary, team_id, name),
    }


def _line_score(competitor: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in competitor.get("linescores") or []:
        period = _to_int(item.get("period"))
        rows.append(
            {
                "period": period,
                "label": _period_label(period),
                "points": _to_int(item.get("value")),
                "display": str(item.get("displayValue") or ""),
            }
        )
    return rows


def _period_label(period: int | None) -> str:
    if period is None:
        return ""
    if period <= 4:
        return f"Q{period}"
    return f"OT{period - 4}"


def _team_stats(summary: dict[str, Any], team_id: str, team_name: str) -> dict[str, str]:
    for team_block in (summary.get("boxscore") or {}).get("teams") or []:
        team = team_block.get("team") or {}
        if str(team.get("id")) == team_id or team.get("displayName") == team_name:
            stats = {}
            for stat in team_block.get("statistics") or []:
                label = stat.get("label") or stat.get("abbreviation") or stat.get("name")
                value = stat.get("displayValue")
                if label and value is not None:
                    stats[str(label)] = str(value)
            return stats
    return {}


def _box_score(summary: dict[str, Any], team_id: str, team_name: str) -> list[dict[str, Any]]:
    for block in (summary.get("boxscore") or {}).get("players") or []:
        team = block.get("team") or {}
        if str(team.get("id")) == team_id or team.get("displayName") == team_name:
            stats_block = (block.get("statistics") or [{}])[0]
            labels = [str(label) for label in stats_block.get("labels") or []]
            entries = []
            for athlete in stats_block.get("athletes") or []:
                row = _athlete_row(labels, athlete)
                if row:
                    entries.append(row)
            return entries
    return []


def _athlete_row(labels: list[str], entry: dict[str, Any]) -> dict[str, Any] | None:
    stats = entry.get("stats") or []
    athlete = entry.get("athlete") or {}
    name = athlete.get("displayName") or ""
    if not name or not stats:
        return None
    by_label = {label: str(stats[i]) for i, label in enumerate(labels) if i < len(stats)}
    return {
        "player": name,
        "position": (athlete.get("position") or {}).get("abbreviation") or "",
        "starter": bool(entry.get("starter")),
        "did_not_play": bool(entry.get("didNotPlay")),
        "minutes": by_label.get("MIN", ""),
        "points": _to_int(by_label.get("PTS")) or 0,
        "rebounds": _to_int(by_label.get("REB")) or 0,
        "assists": _to_int(by_label.get("AST")) or 0,
        "turnovers": _to_int(by_label.get("TO")) or 0,
        "steals": _to_int(by_label.get("STL")) or 0,
        "blocks": _to_int(by_label.get("BLK")) or 0,
        "offensive_rebounds": _to_int(by_label.get("OREB")) or 0,
        "defensive_rebounds": _to_int(by_label.get("DREB")) or 0,
        "fg": by_label.get("FG", ""),
        "three_pt": by_label.get("3PT", ""),
        "ft": by_label.get("FT", ""),
        "plus_minus": by_label.get("+/-", ""),
        "raw_stats": by_label,
    }


def _scoring_by_quarter(teams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    periods = sorted({row["period"] for team in teams for row in team.get("line_score", []) if row.get("period")})
    out = []
    for period in periods:
        row: dict[str, Any] = {"period": period, "label": _period_label(period)}
        for team in teams:
            line = next((item for item in team.get("line_score", []) if item.get("period") == period), {})
            row[team["name"]] = line.get("points")
            row[team["abbreviation"]] = line.get("points")
        out.append(row)
    return out


def _leaders(summary: dict[str, Any], teams: list[dict[str, Any]]) -> dict[str, Any]:
    from_summary: dict[str, Any] = {}
    for team_leaders in summary.get("leaders") or []:
        team = team_leaders.get("team") or {}
        name = team.get("displayName") or ""
        categories = {}
        for category in team_leaders.get("leaders") or []:
            cat_name = category.get("displayName") or category.get("name") or ""
            rows = []
            for leader in category.get("leaders") or []:
                athlete = leader.get("athlete") or {}
                rows.append(
                    {
                        "player": athlete.get("displayName") or "",
                        "value": leader.get("displayValue") or str(leader.get("value") or ""),
                        "summary": leader.get("summary") or "",
                    }
                )
            if cat_name and rows:
                categories[cat_name] = rows
        if name:
            from_summary[name] = categories

    computed = {}
    for team in teams:
        computed[team["name"]] = {
            "points": _leaders_from_box(team, "points"),
            "rebounds": _leaders_from_box(team, "rebounds"),
            "assists": _leaders_from_box(team, "assists"),
        }
    return {"espn": from_summary, "computed": computed}


def _leaders_from_box(team: dict[str, Any], stat_key: str) -> list[dict[str, Any]]:
    rows = [row for row in team.get("box_score", []) if not row.get("did_not_play")]
    rows.sort(key=lambda item: int(item.get(stat_key) or 0), reverse=True)
    return [
        {"player": row["player"], "value": row.get(stat_key, 0)}
        for row in rows[:3]
        if int(row.get(stat_key) or 0) > 0
    ]


def _play_by_play(summary: dict[str, Any]) -> dict[str, Any]:
    plays = summary.get("plays") or []
    scoring = []
    notable = []
    for play in plays:
        normalized = _normalize_play(play)
        if not normalized:
            continue
        if normalized["scoring_play"]:
            scoring.append(normalized)
        text = normalized.get("text", "").lower()
        if any(marker in text for marker in ("turnover", "steal", "block", "technical", "flagrant")):
            notable.append(normalized)
    return {
        "available": bool(plays),
        "play_count": len(plays),
        "scoring_play_count": len(scoring),
        "scoring_plays": scoring,
        "notable_plays": notable[:20],
        "last_play": _normalize_play(plays[-1]) if plays else None,
    }


def _normalize_play(play: dict[str, Any]) -> dict[str, Any] | None:
    play_id = play.get("id")
    if not play_id:
        return None
    period = _to_int((play.get("period") or {}).get("number"))
    return {
        "id": str(play_id),
        "period": period,
        "period_label": (play.get("period") or {}).get("displayValue") or _period_label(period),
        "clock": (play.get("clock") or {}).get("displayValue") or "",
        "team_id": str((play.get("team") or {}).get("id") or ""),
        "text": play.get("text") or "",
        "short_description": play.get("shortDescription") or "",
        "scoring_play": bool(play.get("scoringPlay")),
        "score_value": _to_int(play.get("scoreValue")) or 0,
        "away_score": _to_int(play.get("awayScore")) or 0,
        "home_score": _to_int(play.get("homeScore")) or 0,
        "wallclock": play.get("wallclock") or "",
    }


def _gamecast(summary: dict[str, Any]) -> dict[str, Any]:
    winprob = summary.get("winprobability") or []
    return {
        "available": bool(summary.get("plays") or winprob),
        "win_probability_available": bool(winprob),
        "win_probability_samples": len(winprob),
        "article_available": bool(summary.get("article")),
        "video_count": len(summary.get("videos") or []),
    }


def _schedule_context(schedule: dict[str, Any], game_id: str, as_of: str | None) -> dict[str, Any]:
    events = schedule.get("events") or []
    next_event = None
    recent = []
    found = False
    for event in events:
        item = {
            "id": str(event.get("id") or ""),
            "date": _event_date(event),
            "name": event.get("name") or "",
            "short_name": event.get("shortName") or "",
        }
        if item["id"] == game_id:
            found = True
            continue
        if not found:
            recent.append(item)
        elif next_event is None:
            next_event = item
            break
    return {
        "as_of": as_of,
        "team_record_summary": (schedule.get("team") or {}).get("recordSummary") or "",
        "standing_summary": (schedule.get("team") or {}).get("standingSummary") or "",
        "event_count": len(events),
        "previous_events": recent[-3:],
        "next_event": next_event,
    }


def _sources(payloads: dict[str, Any], game_id: str, game_date: str, retrieved_at: str) -> list[dict[str, str]]:
    return [
        {
            "name": "ESPN Mystics schedule",
            "url": payloads.get("schedule_url") or SCHEDULE_URL_TMPL.format(season=game_date[:4]),
            "retrieved_at": retrieved_at,
        },
        {
            "name": "ESPN WNBA scoreboard",
            "url": payloads.get("scoreboard_url") or "",
            "retrieved_at": retrieved_at,
        },
        {
            "name": "ESPN WNBA summary/gamecast",
            "url": payloads.get("summary_url") or SUMMARY_URL_TMPL.format(event_id=game_id),
            "retrieved_at": retrieved_at,
        },
    ]
