#!/usr/bin/env python3
"""Refresh team KBs from ESPN.

Pulls live data from ESPN's site.api endpoints for each team in
generate_content.ALL_TEAMS and merges into the corresponding
`data/teams/{slug}.json` file. Only refreshes the time-sensitive fields
(current_record, roster, recent_games, upcoming_games, last_updated).
Time-stable fields (venue, ownership, conference, founded, head_coach.title,
head_coach.background, head_coach.tenure_start, coaching_staff,
roster[].notes, rivalries, sources, verification_notes) are PRESERVED.

CLI:
  python scripts/refresh_kb.py                  # refresh all in-season teams
  python scripts/refresh_kb.py --team nationals # one team
  python scripts/refresh_kb.py --dry-run        # print diff, don't write
  python scripts/refresh_kb.py --include-offseason  # also refresh out-of-season teams

Designed to run on a schedule (weekly cron / GH Actions). Pure HTTP — no
LLM calls, no API cost.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from generate_content import ALL_TEAMS, in_season, team_slug  # noqa: E402

UA = {"User-Agent": "NSMT-KB-Refresh/0.1 (+https://thensmt.com)"}
TEAM_INFO_TMPL     = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_slug}/teams/{team_id}"
TEAM_ROSTER_TMPL   = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_slug}/teams/{team_id}/roster"
TEAM_SCHEDULE_TMPL = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_slug}/teams/{team_id}/schedule"

# Teams whose season is over even if their league is still in season window
# (eliminated from playoffs). Mirrors generate_baselines.FORCE_OFFSEASON_SLUGS.
ELIMINATED_SLUGS = {"wizards", "capitals"}

# Per-team KB fields that the refresh script is ALLOWED to update. Anything
# else (venue, ownership, conference, etc.) is preserved verbatim.
REFRESHABLE_FIELDS = {
    "current_record",
    "roster",
    "recent_games",
    "upcoming_games",
    "last_updated",
    "sources",
}


def refresh_team(team: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """Refresh one team's KB. Returns a diff dict describing what changed."""
    slug = team_slug(team)
    if not slug:
        return {"slug": "?", "status": "skipped", "reason": "no slug resolved"}

    kb_path = PROJECT_ROOT / "data" / "teams" / f"{slug}.json"
    if not kb_path.exists():
        return {"slug": slug, "status": "skipped", "reason": "KB file missing"}

    kb = json.loads(kb_path.read_text())
    sport = team.get("sport", "")
    league_slug = team.get("league_slug", "")
    team_id = str(team.get("espn_id", "") or kb.get("espn_id", "") or "")

    if not (sport and league_slug and team_id):
        return {"slug": slug, "status": "skipped",
                "reason": f"missing sport={sport!r} league_slug={league_slug!r} team_id={team_id!r}"}

    diff: dict[str, Any] = {"slug": slug, "status": "ok", "changed": []}

    # 1. Team info → current_record.
    # Don't clobber rich/curated record strings with ESPN's terse W-L-T. If the
    # existing record is significantly longer than what ESPN returns (suggesting
    # the KB curator added context like points totals, standings position, tie-
    # breaker explanations, championship-cup notes), we preserve it. The
    # refresh only updates current_record when the existing one is short
    # (under 50 chars) — basic W-L records that have nothing to lose.
    info = _safe_get(TEAM_INFO_TMPL.format(sport=sport, league_slug=league_slug, team_id=team_id))
    if info:
        new_record = _extract_record(info)
        existing_record = kb.get("current_record") or ""
        if new_record and new_record != existing_record:
            if len(existing_record) > 50 and len(new_record) < len(existing_record) // 2:
                diff["changed"].append({
                    "field": "current_record",
                    "summary": "PRESERVED — existing record has curated context "
                               f"({len(existing_record)} chars) richer than ESPN's "
                               f"terse W-L ({len(new_record)} chars)",
                    "preserved": True,
                })
            else:
                diff["changed"].append({"field": "current_record",
                                         "before": existing_record,
                                         "after": new_record})
                kb["current_record"] = new_record

    # 2. Roster → merge by name, preserving notes.
    # Safety guard: if the fetched roster has <30% accent-insensitive name
    # overlap with the existing roster (and the existing roster isn't tiny),
    # refuse to overwrite — likely the espn_id points at a different team.
    # This catches the failure mode from 2026-05-22 where the Mystics' TEAMS
    # entry had espn_id "14" (Seattle Storm's ID) and a naive refresh would
    # have clobbered the Mystics roster with Storm players.
    roster_payload = _safe_get(TEAM_ROSTER_TMPL.format(sport=sport, league_slug=league_slug, team_id=team_id))
    if roster_payload:
        new_roster = _extract_roster(roster_payload, kb.get("roster") or [])
        existing_roster = kb.get("roster") or []
        if new_roster and len(existing_roster) >= 5:
            existing_norms = {_normalize_name(p.get("name", "")) for p in existing_roster}
            new_norms = {_normalize_name(p.get("name", "")) for p in new_roster}
            overlap = len(existing_norms & new_norms)
            overlap_pct = overlap / max(len(existing_norms), 1)
            if overlap_pct < 0.3:
                diff["changed"].append({
                    "field": "roster",
                    "summary": (f"REFUSED — {overlap}/{len(existing_norms)} name overlap "
                                f"({overlap_pct:.0%}); espn_id may be wrong"),
                    "warning": True,
                })
                new_roster = None  # don't apply
        if new_roster and new_roster != existing_roster:
            before_names = sorted(p.get("name", "") for p in existing_roster)
            after_names = sorted(p.get("name", "") for p in new_roster)
            added = sorted(set(after_names) - set(before_names))
            removed = sorted(set(before_names) - set(after_names))
            diff["changed"].append({"field": "roster",
                                     "summary": f"{len(new_roster)} players (was {len(existing_roster)})",
                                     "added": added,
                                     "removed": removed})
            kb["roster"] = new_roster

    # 3. Schedule → recent_games + upcoming_games
    sched_payload = _safe_get(TEAM_SCHEDULE_TMPL.format(sport=sport, league_slug=league_slug, team_id=team_id))
    if sched_payload:
        recent, upcoming = _extract_schedule(sched_payload, team_id)
        if recent and recent != kb.get("recent_games"):
            diff["changed"].append({"field": "recent_games",
                                     "before_count": len(kb.get("recent_games") or []),
                                     "after_count": len(recent),
                                     "newest_after": recent[0].get("date") if recent else None})
            kb["recent_games"] = recent
        if upcoming and upcoming != kb.get("upcoming_games"):
            diff["changed"].append({"field": "upcoming_games",
                                     "before_count": len(kb.get("upcoming_games") or []),
                                     "after_count": len(upcoming)})
            kb["upcoming_games"] = upcoming

    if diff["changed"]:
        kb["last_updated"] = date.today().isoformat()
        # Append to sources (or initialize) — record this refresh run
        sources = kb.get("sources") or []
        refresh_source = {
            "url": TEAM_INFO_TMPL.format(sport=sport, league_slug=league_slug, team_id=team_id),
            "scraped_at": kb["last_updated"],
            "notes": "Auto-refresh: record, roster, recent_games, upcoming_games"
        }
        # Replace any prior auto-refresh entry rather than accumulating
        sources = [s for s in sources if "Auto-refresh" not in (s.get("notes") or "")]
        sources.append(refresh_source)
        kb["sources"] = sources

        if not dry_run:
            kb_path.write_text(json.dumps(kb, indent=2, ensure_ascii=False) + "\n")
    else:
        diff["status"] = "no changes"

    return diff


# ── ESPN payload extraction ───────────────────────────────────────────────────

def _safe_get(url: str) -> dict[str, Any] | None:
    try:
        resp = requests.get(url, headers=UA, timeout=15)
        if not resp.ok:
            logging.warning("HTTP %s for %s", resp.status_code, url)
            return None
        return resp.json()
    except Exception as exc:
        logging.warning("Fetch failed for %s: %s", url, exc)
        return None


def _extract_record(info: dict[str, Any]) -> str:
    """Return a 'W-L (X-Y home, A-B away) as of YYYY-MM-DD' record string from ESPN team info."""
    t = info.get("team") or {}
    record_items = (t.get("record") or {}).get("items") or []
    overall = next((i.get("summary") for i in record_items
                    if (i.get("description") or "").lower() == "overall record"), None)
    home = next((i.get("summary") for i in record_items
                 if (i.get("description") or "").lower() == "home record"), None)
    away = next((i.get("summary") for i in record_items
                 if (i.get("description") or "").lower() == "away record"), None)
    if not overall:
        return ""
    parts = [overall]
    splits = []
    if home:
        splits.append(f"{home} home")
    if away:
        splits.append(f"{away} away")
    if splits:
        parts.append(f"({', '.join(splits)})")
    parts.append(f"as of {date.today().isoformat()}")
    return " ".join(parts)


def _normalize_name(name: str) -> str:
    """Strip diacritics + lowercase for accent-insensitive name matching.
    ESPN's API returns unaccented player names while KB files often have the
    proper accented versions ('Andrés Chaparro' vs ESPN's 'Andres Chaparro').
    We want a refresh to PRESERVE the KB's accented spelling rather than
    overwrite it with ESPN's unaccented one."""
    if not name:
        return ""
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _extract_roster(payload: dict[str, Any], existing_roster: list[dict]) -> list[dict]:
    """Flatten ESPN's per-position-group roster into a single list.

    Two preservation rules to avoid regressing on data the KB already has
    correct:
    1. `notes` on each player is preserved (by accent-insensitive name match).
    2. If the existing KB has an accented spelling of a name that matches
       ESPN's unaccented version, KEEP the KB's spelling. ESPN's API drops
       diacritics; the KB shouldn't lose them on every refresh.
    """
    # Build a lookup keyed by normalized (unaccented, lower) name → original KB record
    existing_by_norm = {}
    for p in existing_roster:
        nm = p.get("name") or ""
        if nm:
            existing_by_norm[_normalize_name(nm)] = p

    out: list[dict] = []
    seen_norms: set[str] = set()
    blocks = payload.get("athletes") or []
    # ESPN can return either grouped (position blocks with .items) or flat.
    if blocks and isinstance(blocks[0], dict) and "items" in blocks[0]:
        for blk in blocks:
            for item in blk.get("items") or []:
                row = _roster_entry(item, existing_by_norm)
                if row and row["_norm"] not in seen_norms:
                    seen_norms.add(row.pop("_norm"))
                    out.append(row)
    else:
        for item in blocks:
            row = _roster_entry(item, existing_by_norm)
            if row and row["_norm"] not in seen_norms:
                seen_norms.add(row.pop("_norm"))
                out.append(row)
    return out


def _roster_entry(item: dict[str, Any], existing_by_norm: dict) -> dict | None:
    espn_name = item.get("fullName") or item.get("displayName")
    if not espn_name:
        return None
    norm = _normalize_name(espn_name)
    existing = existing_by_norm.get(norm) or {}
    # Prefer the KB's spelling when an accent-insensitive match exists; fall
    # back to ESPN's spelling for new players.
    name = existing.get("name") or espn_name
    position = ((item.get("position") or {}).get("abbreviation")
                or (item.get("position") or {}).get("displayName") or "")
    number = item.get("jersey") or ""
    note = existing.get("notes")  # preserved across refresh
    return {"name": name, "position": position, "number": str(number) if number else "",
            "notes": note, "_norm": norm}


def _extract_schedule(payload: dict[str, Any], team_id: str) -> tuple[list[dict], list[dict]]:
    """Split ESPN team schedule events into (recent_games, upcoming_games).
    Recent = completed games, last 5 most-recent first. Upcoming = next 5."""
    events = payload.get("events") or []
    today = date.today()
    recent: list[dict] = []
    upcoming: list[dict] = []
    for event in events:
        comp = (event.get("competitions") or [{}])[0]
        competitors = comp.get("competitors") or []
        us = None
        opp = None
        for c in competitors:
            t = c.get("team") or {}
            if str(t.get("id")) == team_id:
                us = c
            else:
                opp = c
        if not us or not opp:
            continue
        date_str = event.get("date") or ""
        try:
            event_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
        except Exception:
            continue
        opp_name = (opp.get("team") or {}).get("displayName", "")
        venue = "home" if us.get("homeAway") == "home" else "away"
        status_type = ((event.get("status") or {}).get("type") or {})
        is_completed = status_type.get("completed", False)

        if is_completed:
            our_score = _score_val(us)
            opp_score = _score_val(opp)
            winner = us.get("winner")
            if winner is True:
                result = f"W {our_score}-{opp_score}"
            elif winner is False:
                result = f"L {our_score}-{opp_score}"
            else:
                result = f"{our_score}-{opp_score}"
            recent.append({"date": event_date.isoformat(), "opponent": opp_name,
                           "result": result, "venue": venue, "notes": None})
        elif event_date >= today:
            upcoming.append({"date": event_date.isoformat(), "opponent": opp_name,
                             "venue": venue, "start_time_et": None})

    recent.sort(key=lambda g: g["date"], reverse=True)
    upcoming.sort(key=lambda g: g["date"])
    return recent[:5], upcoming[:5]


def _score_val(competitor: dict[str, Any]) -> str:
    score = competitor.get("score")
    if isinstance(score, dict):
        return str(score.get("displayValue") or score.get("value") or "?")
    return str(score or "?")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Refresh team KBs from ESPN.")
    parser.add_argument("--team", help="Single team slug. Default: all teams.")
    parser.add_argument("--dry-run", action="store_true", help="Print diff but don't write.")
    parser.add_argument("--include-offseason", action="store_true",
                        help="Also refresh teams whose league is out of season today.")
    parser.add_argument("--include-eliminated", action="store_true",
                        help="Also refresh teams marked as eliminated (wizards, capitals).")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    today = date.today()
    teams_to_refresh = []
    for team in ALL_TEAMS:
        slug = team_slug(team)
        if args.team and slug != args.team:
            continue
        if not args.include_offseason and not in_season(team, today):
            continue
        if not args.include_eliminated and slug in ELIMINATED_SLUGS:
            continue
        teams_to_refresh.append(team)

    print(f"=== KB Refresh — {len(teams_to_refresh)} team(s) ===")
    print(f"Date: {today.isoformat()}  ·  dry_run: {args.dry_run}")
    print()

    for team in teams_to_refresh:
        diff = refresh_team(team, dry_run=args.dry_run)
        status = diff.get("status")
        changed = diff.get("changed") or []
        if status == "skipped":
            print(f"  {diff['slug']:25s} SKIP — {diff.get('reason')}")
        elif status == "no changes":
            print(f"  {diff['slug']:25s} no changes")
        else:
            applied = [c for c in changed if not c.get("preserved") and not c.get("warning")]
            print(f"  {diff['slug']:25s} updated ({len(applied)} of {len(changed)} field{'s' if len(changed) != 1 else ''}):")
            for change in changed:
                field = change.get("field")
                if change.get("warning"):
                    print(f"      ⚠️  {field}: {change.get('summary')}")
                elif change.get("preserved"):
                    print(f"      ↷ {field}: {change.get('summary')}")
                elif field == "current_record":
                    print(f"      record: {change.get('before')!r} -> {change.get('after')!r}")
                elif field == "roster":
                    print(f"      roster: {change.get('summary')}")
                    if change.get("added"):
                        print(f"        added: {change['added']}")
                    if change.get("removed"):
                        print(f"        removed: {change['removed']}")
                elif field == "recent_games":
                    print(f"      recent_games: {change.get('before_count')} -> {change.get('after_count')}"
                          f" (newest: {change.get('newest_after')})")
                elif field == "upcoming_games":
                    print(f"      upcoming_games: {change.get('before_count')} -> {change.get('after_count')}")

    print()
    if args.dry_run:
        print("Dry run — no files written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
