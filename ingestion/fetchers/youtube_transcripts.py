"""YouTube transcript acquisition for the Mystics beat (Mac-side / residential IP).

Stage 2 proved transcript fetches are 100% blocked from GitHub Actions (Azure)
egress IPs but work from a residential IP. So this module is intended to run
Mac-side, alongside the existing Codex launchd jobs, and is NOT imported by any
CI-run path. It depends on `youtube-transcript-api` (transcript fetch) and,
optionally, `yt-dlp` or a YouTube Data API key (channel discovery only) — none
of which are added to CI's install step.

Stage A scope: acquisition + name correction only. No LLM write step.

Public surface
--------------
- ``fetch_transcript(video_id, kind, ...)`` -> per-video dict (``status`` "ok"/"missing")
- ``fetch_transcripts(videos)`` -> list of per-video dicts
- ``build_media_transcripts(videos, ...)`` -> fetched + name-corrected per-video dicts
- ``discover_game_videos(game_date, team_names, ...)`` -> ``[{"video_id", "kind"}, ...]``
- ``load_roster_name_tokens(...)`` / ``make_name_corrector(...)`` / ``correct_video_names(...)``

A per-video failure (blocked IP, missing transcript, etc.) is recorded as a
``{"status": "missing", "reason": ...}`` record and logged — it never raises, so
one bad video cannot crash a run.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import subprocess
from typing import Any, Callable, Iterable

from ingestion.cache import iso_utc
from newsroom.common import PROJECT_ROOT

try:  # transcript fetch is residential-only; import must not break CI/tests
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api import (
        IpBlocked,
        NoTranscriptFound,
        PoTokenRequired,
        RequestBlocked,
        TranscriptsDisabled,
    )

    _YTA_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised only without the dep
    YouTubeTranscriptApi = None  # type: ignore[assignment]
    # Bind exception names to Exception so the except clauses below stay valid
    # even when the library is absent (those clauses are never reached because
    # fetch_transcript early-returns when YouTubeTranscriptApi is None).
    IpBlocked = RequestBlocked = PoTokenRequired = TranscriptsDisabled = NoTranscriptFound = Exception  # type: ignore[assignment,misc]
    _YTA_IMPORT_ERROR = exc

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

VIDEO_URL_TMPL = "https://www.youtube.com/watch?v={video_id}"
DEFAULT_LANGUAGES = ("en",)

# kinds an editor cares about; classification + schema both use this set
MEDIA_TRANSCRIPT_KINDS = ("highlights", "presser")

# Channel allowlist for discovery (off the manual-override critical path).
# WNBA official id resolved via yt-dlp from the @WNBA handle on 2026-05-29.
CHANNEL_ALLOWLIST: dict[str, dict[str, str]] = {
    "monumental": {"channel_id": "UCiGMk7s-2DCVQaMRzyhi94w", "name": "Monumental Sports Network"},
    "mystics": {"channel_id": "UCRha9IKwKJc3i4fZdstGsvQ", "name": "Washington Mystics"},
    "wnba": {"channel_id": "UCO9a_ryN_l7DIDS-VIt-zmw", "name": "WNBA"},
}

# Name correction tuning. Verified against the two Stage-1 transcripts: catches
# Amore->Amoore, Flores->Florez, Shakir->Shakira, Catron->Citron, Sonya->Sonia
# while leaving the correct possessive "Michaela's" untouched.
NAME_MIN_LEN = 4
NAME_MATCH_CUTOFF = 0.80

# Title keyword classification for discovery.
_PRESSER_MARKERS = ("press conference", "presser", "postgame", "post-game", "post game", "media availability", "availability", "press avail")
_HIGHLIGHT_MARKERS = ("highlights", "full game", "extended highlights", "game highlights", "condensed")

_TOKEN_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_NAME_PART_RE = re.compile(r"^[A-Za-z'-]+$")


# ── Transcript fetch ───────────────────────────────────────────────────────────

def _missing(video_id: str, kind: str, source_url: str, retrieved_at: str, reason: str) -> dict[str, Any]:
    return {
        "video_id": video_id,
        "kind": kind,
        "status": "missing",
        "reason": reason,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
    }


def fetch_transcript(
    video_id: str,
    kind: str,
    *,
    languages: Iterable[str] = DEFAULT_LANGUAGES,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Fetch one video's transcript via the youtube-transcript-api v1.x instance API.

    Returns a per-video dict. On any failure (blocked IP, disabled/absent
    transcript, missing dependency, or unexpected error) returns a ``status:
    "missing"`` record with a human-readable ``reason`` instead of raising.
    """
    retrieved = retrieved_at or iso_utc()
    source_url = VIDEO_URL_TMPL.format(video_id=video_id)

    if YouTubeTranscriptApi is None:
        reason = f"youtube-transcript-api not installed: {_YTA_IMPORT_ERROR}"
        logger.warning("transcript %s (%s): %s", video_id, kind, reason)
        return _missing(video_id, kind, source_url, retrieved, reason)

    try:
        api = YouTubeTranscriptApi()
        listing = api.list(video_id)
        transcript = listing.find_transcript(list(languages))
        fetched = transcript.fetch()
        raw = fetched.to_raw_data()
        segments = [
            {
                "start": float(snippet.get("start") or 0.0),
                "duration": float(snippet.get("duration") or 0.0),
                "text": str(snippet.get("text") or ""),
            }
            for snippet in raw
        ]
        text = " ".join(seg["text"] for seg in segments).strip()
        logger.info(
            "transcript %s (%s): %s track, %d snippets, %d chars",
            video_id, kind, "auto" if transcript.is_generated else "manual", len(segments), len(text),
        )
        return {
            "video_id": video_id,
            "kind": kind,
            "status": "ok",
            "track": "auto" if transcript.is_generated else "manual",
            "language": transcript.language_code,
            "snippet_count": len(segments),
            "char_count": len(text),
            "segments": segments,
            "text": text,
            "source_url": source_url,
            "retrieved_at": retrieved,
        }
    except (IpBlocked, RequestBlocked) as exc:
        reason = f"{type(exc).__name__}: datacenter/IP blocked"
    except PoTokenRequired as exc:
        reason = f"PoTokenRequired: proof-of-origin token required ({exc})"
    except (TranscriptsDisabled, NoTranscriptFound) as exc:
        reason = f"{type(exc).__name__}: no usable transcript"
    except Exception as exc:  # never let one video crash the run
        reason = f"{type(exc).__name__}: {exc}"

    logger.warning("transcript %s (%s) failed: %s", video_id, kind, reason)
    return _missing(video_id, kind, source_url, retrieved, reason)


def _normalize_video_inputs(videos: Iterable[Any]) -> list[tuple[str, str]]:
    """Accept ``[{"video_id","kind"}, ...]`` or ``[(video_id, kind), ...]``."""
    out: list[tuple[str, str]] = []
    for item in videos or []:
        if isinstance(item, dict):
            vid = str(item.get("video_id") or "").strip()
            kind = str(item.get("kind") or "").strip()
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            vid, kind = str(item[0]).strip(), str(item[1]).strip()
        else:
            logger.warning("ignoring unrecognized video input: %r", item)
            continue
        if vid and kind:
            out.append((vid, kind))
        else:
            logger.warning("ignoring video input missing video_id/kind: %r", item)
    return out


def fetch_transcripts(
    videos: Iterable[Any],
    *,
    languages: Iterable[str] = DEFAULT_LANGUAGES,
    retrieved_at: str | None = None,
    fetcher: Callable[..., dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Fetch transcripts for several ``{video_id, kind}`` inputs (no name correction)."""
    retrieved = retrieved_at or iso_utc()
    fetch = fetcher or fetch_transcript
    return [
        fetch(vid, kind, languages=languages, retrieved_at=retrieved)
        for vid, kind in _normalize_video_inputs(videos)
    ]


# ── Name correction (apply before storing; raw is always preserved) ─────────────

def load_roster_name_tokens(
    team_slugs: Iterable[str] = ("mystics",),
    *,
    extra_names: Iterable[str] = (),
    include_staff: bool = False,
) -> dict[str, str]:
    """Collect canonical name tokens from team KB rosters for fuzzy matching.

    Returns ``{lowercased_token: canonical_token}``. Reads ``data/teams/{slug}.json``
    for each slug (opponent KBs included when available); missing/invalid files are
    skipped silently. Tokens shorter than ``NAME_MIN_LEN`` are ignored.

    Defaults to ROSTER PLAYERS ONLY (per the spec). Coaching-staff names are
    excluded by default because short staff surnames collide with common words —
    e.g. "Turner" would pull "turn"/"turned" toward it. Pass ``include_staff=True``
    to also match head coach / assistant names.
    """
    tokens: dict[str, str] = {}

    def add_name(full: Any) -> None:
        for part in str(full or "").split():
            clean = part.strip(".,")
            if len(clean) >= NAME_MIN_LEN and _NAME_PART_RE.match(clean):
                tokens.setdefault(clean.lower(), clean)

    for slug in team_slugs:
        path = PROJECT_ROOT / "data" / "teams" / f"{slug}.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("name tokens: could not read %s: %s", path, exc)
            continue
        for player in data.get("roster") or []:
            add_name(player.get("name"))
        if include_staff:
            add_name((data.get("head_coach") or {}).get("name"))
            for coach in data.get("coaching_staff") or []:
                add_name(coach.get("name"))
    for name in extra_names:
        add_name(name)
    return tokens


def _case_like(template: str, canonical: str) -> str:
    if template.isupper():
        return canonical.upper()
    if template[:1].isupper():
        return canonical[:1].upper() + canonical[1:]
    return canonical.lower()


def _correct_text(text: str, name_tokens: dict[str, str]) -> tuple[str, list[tuple[str, str]]]:
    """Fuzzy-correct name-like tokens in ``text`` against ``name_tokens``.

    Conservative on purpose: only corrects a token that (a) is >= NAME_MIN_LEN,
    (b) is not already a known name, (c) fuzzy-matches a known token at >=
    NAME_MATCH_CUTOFF, and (d) shares the same first letter as that match (this
    last guard blocks false positives like "more" -> "amoore"). Possessives are
    preserved ("Amore's" -> "Amoore's").
    """
    if not name_tokens or not text:
        return text, []
    keys = list(name_tokens.keys())
    corrections: list[tuple[str, str]] = []

    def repl(match: re.Match[str]) -> str:
        word = match.group(0)
        core, suffix = word, ""
        for poss in ("'s", "'S", "'"):
            if core.endswith(poss):
                core, suffix = core[: -len(poss)], word[len(core) - len(poss):]
                break
        corel = core.lower()
        if len(core) < NAME_MIN_LEN or corel in name_tokens:
            return word
        candidates = difflib.get_close_matches(corel, keys, n=1, cutoff=NAME_MATCH_CUTOFF)
        if not candidates or candidates[0][:1] != corel[:1]:
            return word
        new_word = _case_like(core, name_tokens[candidates[0]]) + suffix
        if new_word != word:
            corrections.append((word, new_word))
        return new_word

    return _TOKEN_RE.sub(repl, text), corrections


def make_name_corrector(name_tokens: dict[str, str]) -> Callable[[str], tuple[str, list[tuple[str, str]]]]:
    """Return a ``correct(text) -> (corrected_text, [(from, to), ...])`` closure."""
    def corrector(text: str) -> tuple[str, list[tuple[str, str]]]:
        return _correct_text(text, name_tokens)
    return corrector


def correct_video_names(video: dict[str, Any], name_tokens: dict[str, str]) -> dict[str, Any]:
    """Add ``corrected_segments``/``corrected_text``/``name_corrections`` to a video.

    Raw ``segments``/``text`` are preserved unchanged (quote verification later
    needs ground truth). Missing-status videos are returned unchanged.
    """
    if video.get("status") != "ok":
        return video
    counts: dict[tuple[str, str], int] = {}
    corrected_segments: list[dict[str, Any]] = []
    for seg in video.get("segments") or []:
        new_text, corrections = _correct_text(str(seg.get("text") or ""), name_tokens)
        corrected_segments.append(
            {"start": seg.get("start", 0.0), "duration": seg.get("duration", 0.0), "text": new_text}
        )
        for pair in corrections:
            counts[pair] = counts.get(pair, 0) + 1
    out = dict(video)
    out["corrected_segments"] = corrected_segments
    out["corrected_text"] = " ".join(seg["text"] for seg in corrected_segments).strip()
    out["name_corrections"] = [
        {"from": frm, "to": to, "count": count}
        for (frm, to), count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return out


def build_media_transcripts(
    videos: Iterable[Any],
    *,
    name_tokens: dict[str, str] | None = None,
    team_slugs: Iterable[str] = ("mystics",),
    languages: Iterable[str] = DEFAULT_LANGUAGES,
    retrieved_at: str | None = None,
    fetcher: Callable[..., dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Fetch + name-correct transcripts for ``{video_id, kind}`` inputs.

    ``fetcher`` is injectable for tests (defaults to the real network fetcher).
    ``name_tokens`` defaults to the roster tokens loaded from ``team_slugs``.
    """
    tokens = name_tokens if name_tokens is not None else load_roster_name_tokens(team_slugs)
    fetched = fetch_transcripts(videos, languages=languages, retrieved_at=retrieved_at, fetcher=fetcher)
    return [correct_video_names(video, tokens) for video in fetched]


# ── Channel discovery (off the manual-override critical path) ────────────────────

def _classify_kind(title: str) -> str | None:
    lowered = (title or "").lower()
    if any(marker in lowered for marker in _PRESSER_MARKERS):
        return "presser"
    if any(marker in lowered for marker in _HIGHLIGHT_MARKERS):
        return "highlights"
    return None


def _title_team_tokens(team_names: Iterable[str]) -> list[set[str]]:
    """One token-set per team (e.g. {"washington","mystics"}); a title must hit
    at least one distinctive token from EACH team."""
    stop = {"the", "of", "fc", "sc"}
    sets: list[set[str]] = []
    for name in team_names:
        toks = {tok for tok in re.findall(r"[a-z]+", (name or "").lower()) if len(tok) >= 3 and tok not in stop}
        if toks:
            sets.append(toks)
    return sets


def _title_matches_teams(title: str, team_token_sets: list[set[str]]) -> bool:
    lowered_tokens = set(re.findall(r"[a-z]+", (title or "").lower()))
    return all(bool(team & lowered_tokens) for team in team_token_sets) if team_token_sets else False


def _date_close(upload_date: str | None, game_date: str, window_days: int) -> bool:
    """Compare YYYYMMDD upload_date to a game date (YYYY-MM-DD or ISO) within a window.
    Unknown upload dates do not disqualify (discovery is best-effort)."""
    if not upload_date:
        return True
    digits = re.sub(r"[^0-9]", "", str(game_date))[:8]
    if len(digits) < 8 or len(str(upload_date)) < 8:
        return True
    try:
        from datetime import date

        up = date(int(upload_date[:4]), int(upload_date[4:6]), int(upload_date[6:8]))
        gm = date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        return abs((up - gm).days) <= window_days
    except ValueError:
        return True


def _list_uploads_ytdlp(channel_id: str, limit: int) -> list[dict[str, Any]]:
    url = f"https://www.youtube.com/channel/{channel_id}/videos"
    proc = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--playlist-end", str(limit), "--dump-json", url],
        capture_output=True, text=True, timeout=90,
    )
    uploads: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        uploads.append({"id": data.get("id"), "title": data.get("title") or "", "upload_date": data.get("upload_date")})
    return uploads


def _resolve_upload_date_ytdlp(video_id: str) -> str | None:
    proc = subprocess.run(
        ["yt-dlp", "--skip-download", "--print", "%(upload_date)s", VIDEO_URL_TMPL.format(video_id=video_id)],
        capture_output=True, text=True, timeout=60,
    )
    value = proc.stdout.strip().splitlines()[0].strip() if proc.stdout.strip() else ""
    return value if re.fullmatch(r"\d{8}", value) else None


def _list_uploads_api(channel_id: str, api_key: str, limit: int) -> list[dict[str, Any]]:
    import requests  # local import: discovery-only, not in CI path

    base = "https://www.googleapis.com/youtube/v3"
    ch = requests.get(
        f"{base}/channels", params={"part": "contentDetails", "id": channel_id, "key": api_key}, timeout=15
    ).json()
    items = ch.get("items") or []
    if not items:
        return []
    uploads_playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    pl = requests.get(
        f"{base}/playlistItems",
        params={"part": "snippet", "playlistId": uploads_playlist, "maxResults": min(limit, 50), "key": api_key},
        timeout=15,
    ).json()
    uploads: list[dict[str, Any]] = []
    for item in pl.get("items") or []:
        snippet = item.get("snippet") or {}
        resource = snippet.get("resourceId") or {}
        published = (snippet.get("publishedAt") or "")[:10].replace("-", "")
        uploads.append(
            {"id": resource.get("videoId"), "title": snippet.get("title") or "", "upload_date": published or None}
        )
    return uploads


def discover_game_videos(
    game_date: str,
    team_names: Iterable[str],
    *,
    channels: dict[str, dict[str, str]] | None = None,
    max_per_channel: int = 25,
    window_days: int = 2,
) -> list[dict[str, Any]]:
    """Discover candidate highlight/presser videos for a game across the allowlist.

    Best-effort and OFF the manual-override critical path. Uses a YouTube Data API
    key when ``YOUTUBE_API_KEY`` is set, otherwise yt-dlp. Returns
    ``[{"video_id", "kind", "title", "channel", "channel_slug", "upload_date"}, ...]``.
    A manual override should be used instead of this when the exact videos are known
    (see ``build_media_transcripts``); this never raises and returns ``[]`` on failure.
    """
    channels = channels or CHANNEL_ALLOWLIST
    api_key = os.environ.get("YOUTUBE_API_KEY")
    team_token_sets = _title_team_tokens(team_names)
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    for slug, meta in channels.items():
        try:
            uploads = (
                _list_uploads_api(meta["channel_id"], api_key, max_per_channel)
                if api_key
                else _list_uploads_ytdlp(meta["channel_id"], max_per_channel)
            )
        except Exception as exc:  # discovery must never crash a run
            logger.warning("discovery: channel %s (%s) failed: %s", slug, meta.get("channel_id"), exc)
            continue

        for upload in uploads:
            video_id = upload.get("id")
            if not video_id or video_id in seen:
                continue
            kind = _classify_kind(upload.get("title", ""))
            if not kind or not _title_matches_teams(upload.get("title", ""), team_token_sets):
                continue
            upload_date = upload.get("upload_date")
            # Flat yt-dlp listings often omit upload_date; resolve it for the few
            # title-matched survivors so the date window is meaningful.
            if upload_date is None and not api_key:
                try:
                    upload_date = _resolve_upload_date_ytdlp(video_id)
                except Exception as exc:
                    logger.info("discovery: upload_date resolve failed for %s: %s", video_id, exc)
            if not _date_close(upload_date, game_date, window_days):
                continue
            seen.add(video_id)
            found.append(
                {
                    "video_id": video_id,
                    "kind": kind,
                    "title": upload.get("title", ""),
                    "channel": meta.get("name", slug),
                    "channel_slug": slug,
                    "upload_date": upload_date,
                }
            )
    return found
