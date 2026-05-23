"""Story packet generator.

Two entry points:

- `build_story_packet("mystics", ...)` — the original Mystics-only path. Uses
  the layered Mystics fetchers (ESPN, WNBA.com, mystics official site, reddit
  stub) and emits a packet with the legacy basketball boxscore shape (`rows`).
  Don't touch this path — the existing test suite covers it.

- `build_story_packet_for_team(team_slug, ...)` — the generic path for any
  team in generate_content.ALL_TEAMS. Uses `ingestion.fetchers.espn_generic`
  (sport-parameterized) and emits a packet with the new sport-neutral
  boxscore shape (`entries`). This is what new sports (MLB, NFL, NHL, MLS,
  NWSL, UFL) flow through.

CLI accepts either path via `--team <slug>`. Mystics goes through the legacy
path; everything else goes through the generic path.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from ingestion.cache import iso_utc
from ingestion.fetchers import espn, espn_generic, mystics_official, reddit_stub, wnba_com
from ingestion.schema import StoryPacket
from ingestion.validators import validate_packet


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEAM_SLUG = "mystics"
TEAM_NAME = "Washington Mystics"
LEAGUE = "WNBA"

Fetcher = Callable[[date, str], dict[str, Any]]

DEFAULT_FETCHERS: dict[str, Callable[..., Any]] = {
    "espn": espn.fetch,
    "wnba_com": wnba_com.fetch,
    "mystics_official": mystics_official.fetch,
    "reddit": reddit_stub.fetch,
}


def build_story_packet(
    team: str,
    target_date: date,
    *,
    retrieved_at: str | None = None,
    fetchers: dict[str, Callable[..., Any]] | None = None,
) -> StoryPacket:
    if team != TEAM_SLUG:
        raise ValueError("Story packet MVP supports only --team mystics")

    retrieved = retrieved_at or iso_utc()
    active_fetchers = fetchers or DEFAULT_FETCHERS
    kb = _load_team_kb()

    espn_data = _safe_fetch(active_fetchers.get("espn"), target_date, retrieved, "ESPN")
    wnba_data = _safe_fetch(active_fetchers.get("wnba_com"), target_date, retrieved, "WNBA.com")
    official_data = _safe_fetch(
        active_fetchers.get("mystics_official"),
        target_date,
        retrieved,
        "Washington Mystics official site",
    )
    reddit_items = _safe_reddit(active_fetchers.get("reddit"), target_date, retrieved)

    game_summary = espn_data.get("game_summary") or wnba_data.get("game_summary")
    top_performers = _first_non_empty(espn_data.get("top_performers"), wnba_data.get("top_performers"))
    standings_context = wnba_data.get("standings_context") or _kb_standings_context(kb)
    recent_news = official_data.get("recent_news_items") or []
    injuries = wnba_data.get("injuries_or_availability") or []
    source_links = _dedupe_sources(
        (espn_data.get("source_links") or [])
        + (wnba_data.get("source_links") or [])
        + (official_data.get("source_links") or [])
    )

    confidence_notes = _clean_strings(
        (espn_data.get("confidence_notes") or [])
        + (wnba_data.get("confidence_notes") or [])
        + (official_data.get("confidence_notes") or [])
    )
    if reddit_items:
        confidence_notes.append("Reddit community items were returned by a non-default fetcher; verify attribution before use")

    event_type = "game" if game_summary else "off_day"
    if event_type == "off_day":
        no_game_note = f"no game played on {target_date.isoformat()}"
        if no_game_note not in confidence_notes:
            confidence_notes.insert(0, no_game_note)

    packet: StoryPacket = {
        "team": TEAM_NAME,
        "league": LEAGUE,
        "event_type": event_type,
        "retrieved_at": retrieved,
        "kb_slug": TEAM_SLUG,
        "game_summary": game_summary,
        "top_performers": top_performers,
        "recent_team_context": _recent_team_context(event_type, game_summary, espn_data, kb, target_date),
        "key_players": _key_players(kb, top_performers),
        "injuries_or_availability": injuries,
        "standings_context": standings_context,
        "recent_news_items": recent_news,
        "editorial_angle_candidates": _angle_candidates(
            event_type, game_summary, standings_context, recent_news, espn_data
        ),
        "confidence_notes": confidence_notes,
        "source_links": source_links,
    }
    # Full per-player boxscores from ESPN summary. When present, the writer
    # prompt MUST cite these over training-data recall — that's the fix for
    # the stat-line hallucination class we saw on 2026-05-22.
    if espn_data.get("boxscore") is not None:
        packet["boxscore"] = espn_data["boxscore"]
    if espn_data.get("opponent_boxscore") is not None:
        packet["opponent_boxscore"] = espn_data["opponent_boxscore"]
    validate_packet(packet)
    return packet


def write_packet(packet: StoryPacket, target_date: date, slug: str | None = None) -> Path:
    """Write the packet JSON. `slug` defaults to TEAM_SLUG (mystics) for
    backwards compatibility with the existing CLI; new sports pass their own
    slug so the filename matches the team."""
    output_dir = PROJECT_ROOT / "data" / "packets"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{slug or TEAM_SLUG}_{target_date.isoformat()}.json"
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    return output_path


# ── Generic packet builder (for any team in generate_content.ALL_TEAMS) ──────

def build_story_packet_for_team(team_slug: str, target_date: date,
                                 *, retrieved_at: str | None = None) -> StoryPacket:
    """Build a story packet for any team. Looks the team up in
    generate_content.ALL_TEAMS, fetches ESPN data via espn_generic, loads the
    team's KB for standings + key-players context, and emits a packet whose
    `boxscore` field uses the new sport-neutral `entries` shape."""
    # Local import to avoid pulling generate_content into the ingestion module
    # at import time — keeps test isolation simpler.
    sys.path.insert(0, str(PROJECT_ROOT))
    from generate_content import ALL_TEAMS, team_slug as resolve_slug

    team_dict = None
    for t in ALL_TEAMS:
        if resolve_slug(t) == team_slug:
            team_dict = t
            break
    if not team_dict:
        raise ValueError(f"Unknown team slug: {team_slug!r}. Known slugs: " +
                         ", ".join(sorted({resolve_slug(t) for t in ALL_TEAMS if resolve_slug(t)})))

    retrieved = retrieved_at or iso_utc()
    kb_path = PROJECT_ROOT / "data" / "teams" / f"{team_slug}.json"
    try:
        kb = json.loads(kb_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to load KB at {kb_path}: {exc}") from exc

    espn_data = espn_generic.fetch(
        sport=team_dict["sport"],
        league_slug=team_dict["league_slug"],
        team_id=team_dict["espn_id"],
        team_name=team_dict["name"],
        target_date=target_date,
        retrieved_at=retrieved,
    )

    game_summary = espn_data.get("game_summary")
    top_performers = espn_data.get("top_performers") or []
    event_type = "game" if game_summary else "off_day"

    confidence_notes = list(espn_data.get("confidence_notes") or [])
    if event_type == "off_day":
        no_game_note = f"no game played on {target_date.isoformat()}"
        if no_game_note not in confidence_notes:
            confidence_notes.insert(0, no_game_note)

    packet: StoryPacket = {
        "team": team_dict["name"],
        "league": team_dict["league"],
        "event_type": event_type,
        "retrieved_at": retrieved,
        "kb_slug": team_slug,
        "game_summary": game_summary,
        "top_performers": top_performers,
        "recent_team_context": _team_context_or_kb_fallback(
            event_type, game_summary, espn_data, kb, target_date, team_dict["name"]
        ),
        "key_players": _generic_key_players(kb, top_performers),
        "injuries_or_availability": [],
        "standings_context": _generic_standings_context(kb),
        "recent_news_items": [],
        "editorial_angle_candidates": espn_data.get("editorial_angle_candidates") or [],
        "confidence_notes": confidence_notes,
        "source_links": espn_data.get("source_links") or [],
    }

    if espn_data.get("boxscore") is not None:
        packet["boxscore"] = espn_data["boxscore"]
    if espn_data.get("opponent_boxscore") is not None:
        packet["opponent_boxscore"] = espn_data["opponent_boxscore"]

    validate_packet(packet)
    return packet


def _generic_standings_context(kb: dict[str, Any]) -> str:
    record = kb.get("current_record")
    if record:
        return f"KB-listed record (may lag live standings): {record}."
    return ""


def _generic_key_players(kb: dict[str, Any], top_performers: list[dict[str, str]]) -> list[dict[str, str]]:
    """Pull 3-5 key players from top_performers + KB roster. Sport-neutral —
    just uses whatever the boxscore + roster expose."""
    players: list[dict[str, str]] = []
    seen: set[str] = set()
    for performer in top_performers[:3]:
        name = performer.get("player")
        if name and name not in seen:
            seen.add(name)
            players.append({"name": name, "role": "recent top performer"})
    for player in kb.get("roster", []):
        name = player.get("name")
        if not name or name in seen:
            continue
        notes = player.get("notes") or ""
        position = player.get("position") or "player"
        role = position + (f"; {notes}" if notes else "")
        players.append({"name": name, "role": role})
        seen.add(name)
        if len(players) >= 5:
            break
    return players


def _team_context_or_kb_fallback(event_type: str, game_summary: dict | None,
                                  espn_data: dict, kb: dict, target_date: date,
                                  team_name: str) -> str:
    context = espn_data.get("recent_team_context") or ""
    if event_type == "game" and game_summary:
        return context.strip()
    recent_games = kb.get("recent_games") or []
    if recent_games:
        last = recent_games[-1]
        return (
            f"{team_name} was idle on {target_date.isoformat()}. "
            f"The verified KB's latest listed result is {last.get('result', 'unknown')} "
            f"vs {last.get('opponent', 'an opponent')} on {last.get('date', 'a recent date')}."
        )
    return f"{team_name} was idle on {target_date.isoformat()}."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a story packet JSON file for any team in ALL_TEAMS.")
    parser.add_argument("--team", required=True,
                        help="Team slug (e.g. 'mystics', 'nationals'). Mystics uses the legacy "
                             "multi-source fetcher; other teams use the generic ESPN-only path.")
    parser.add_argument("--date", dest="target_date", type=_parse_date, default=date.today())
    parser.add_argument("--dry-run", action="store_true", help="Print validated JSON and do not write a file.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if args.team == TEAM_SLUG:
        packet = build_story_packet(args.team, args.target_date)
    else:
        packet = build_story_packet_for_team(args.team, args.target_date)
    rendered = json.dumps(packet, indent=2, sort_keys=True)
    if args.dry_run:
        print(rendered)
    else:
        output_path = write_packet(packet, args.target_date, slug=args.team)
        print(f"Wrote {output_path.relative_to(PROJECT_ROOT)}")
    return 0


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from exc


def _load_team_kb() -> dict[str, Any]:
    path = PROJECT_ROOT / "data" / "teams" / f"{TEAM_SLUG}.json"
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to load Mystics KB at {path}: {exc}") from exc


def _safe_fetch(
    fetcher: Callable[..., Any] | None,
    target_date: date,
    retrieved_at: str,
    source_label: str,
) -> dict[str, Any]:
    if fetcher is None:
        return {"confidence_notes": [f"{source_label} fetcher not configured"]}
    try:
        result = fetcher(target_date, retrieved_at)
    except Exception as exc:  # pragma: no cover - defensive boundary for live sources
        logging.warning("%s fetcher failed: %s", source_label, exc)
        return {"confidence_notes": [f"{source_label} fetcher failed: {exc}"]}
    if not isinstance(result, dict):
        return {"confidence_notes": [f"{source_label} fetcher returned no structured data"]}
    return result


def _safe_reddit(fetcher: Callable[..., Any] | None, target_date: date, retrieved_at: str) -> list[dict[str, Any]]:
    if fetcher is None:
        return []
    try:
        result = fetcher(target_date, retrieved_at)
    except NotImplementedError as exc:
        logging.info("Reddit fetcher intentionally disabled: %s", exc)
        return []
    except Exception as exc:  # pragma: no cover - defensive boundary for future source
        logging.warning("Reddit fetcher failed: %s", exc)
        return []
    return result if isinstance(result, list) else []


def _first_non_empty(*values: Any) -> list[dict[str, str]]:
    for value in values:
        if isinstance(value, list) and value:
            return value
    return []


def _dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        key = (str(source.get("source_name", "")), str(source.get("source_url", "")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _clean_strings(values: list[Any]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip() and value not in cleaned:
            cleaned.append(value.strip())
    return cleaned


def _kb_standings_context(kb: dict[str, Any]) -> str:
    record = kb.get("current_record")
    if record:
        return f"Live standings were unavailable; the verified team KB lists Washington at {record}."
    return "Live standings were unavailable from public sources."


def _recent_team_context(
    event_type: str,
    game_summary: dict[str, str] | None,
    espn_data: dict[str, Any],
    kb: dict[str, Any],
    target_date: date,
) -> str:
    context = espn_data.get("recent_team_context") or ""
    if event_type == "game" and game_summary:
        opponent = game_summary.get("opponent", "its opponent")
        score = game_summary.get("score", "score unavailable")
        base = f"Washington played {opponent} on {target_date.isoformat()}; listed score: {score}."
        return " ".join(part for part in (base, context) if part).strip()

    recent_games = kb.get("recent_games") or []
    if recent_games:
        last = recent_games[-1]
        return (
            f"Washington was idle on {target_date.isoformat()}. "
            f"The verified KB's latest listed result is {last.get('result', 'unknown')} "
            f"against {last.get('opponent', 'an opponent')} on {last.get('date', 'a recent date')}."
        )
    return f"Washington was idle on {target_date.isoformat()}."


def _key_players(kb: dict[str, Any], top_performers: list[dict[str, str]]) -> list[dict[str, str]]:
    players: list[dict[str, str]] = []
    seen: set[str] = set()

    for performer in top_performers[:3]:
        name = performer.get("player")
        if name and name not in seen:
            seen.add(name)
            players.append({"name": name, "role": "recent top performer"})

    for player in kb.get("roster", []):
        name = player.get("name")
        if not name or name in seen:
            continue
        notes = player.get("notes")
        position = player.get("position") or "player"
        role = f"{position}" + (f"; {notes}" if notes else "")
        players.append({"name": name, "role": role})
        seen.add(name)
        if len(players) >= 5:
            break
    return players


def _angle_candidates(
    event_type: str,
    game_summary: dict[str, str] | None,
    standings_context: str,
    news: list[dict[str, Any]],
    espn_data: dict[str, Any] | None = None,
) -> list[str]:
    if event_type == "game" and game_summary:
        espn_angles = list((espn_data or {}).get("editorial_angle_candidates") or [])
        generic = [
            f"Frame the result around what changed against {game_summary.get('opponent', 'the opponent')}.",
            "Use the listed top performers as the spine of the recap.",
            "Tie the result to the standings context without overstating playoff stakes.",
        ]
        # Prefer data-driven ESPN angles; fall back to generic if ESPN provided none.
        merged: list[str] = []
        for angle in espn_angles + generic:
            if angle and angle not in merged:
                merged.append(angle)
            if len(merged) >= 4:
                break
        return merged

    angles = [
        "Use the off day for a standings check and short-term schedule reset.",
        "Build around recent official news while avoiding unsupported injury assumptions.",
    ]
    if standings_context:
        angles.append("Explain what the current standings context means for the next game.")
    if news:
        angles.append("Connect the freshest official-news item to the next Mystics storyline.")
    return angles[:4]


if __name__ == "__main__":
    raise SystemExit(main())

