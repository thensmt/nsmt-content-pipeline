#!/usr/bin/env python3
"""
NSMT transcript acquisition smoke test.

Stage 1: run on your MBP (residential IP). Proves the library + these video IDs work.
Stage 2: run the SAME script inside a GitHub Actions job. Proves whether a
         datacenter IP gets blocked. This is the test that actually matters.

uv run --with youtube-transcript-api test_transcripts.py
"""

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api import (
    IpBlocked,
    RequestBlocked,
    PoTokenRequired,
    TranscriptsDisabled,
    NoTranscriptFound,
)

# The two videos you pulled
VIDEOS = {
    "monumental_highlights": "yvVYc7CfIBo",   # commentary track -> momentum / atmosphere
    "mystics_postgame":      "lZ1U_8wCp6g",   # coach + player voice -> quotes / tone
}


def probe(label: str, video_id: str) -> bool:
    api = YouTubeTranscriptApi()
    try:
        # list() first so we can see what's available + whether it's auto-generated
        tlist = api.list(video_id)
        available = [
            (t.language_code, "auto" if t.is_generated else "manual")
            for t in tlist
        ]
        fetched = api.fetch(video_id, languages=["en"])
        snippets = fetched.to_raw_data()
        text = " ".join(s["text"] for s in snippets)

        print(f"[OK]    {label} ({video_id})")
        print(f"        tracks available : {available}")
        print(f"        snippets fetched : {len(snippets)}")
        print(f"        total characters : {len(text)}")
        print(f"        first line       : {snippets[0]['text']!r}")
        return True

    except (IpBlocked, RequestBlocked) as e:
        # THE failure mode you care about. Expect this is where CI dies.
        print(f"[BLOCKED] {label} ({video_id}) -> datacenter IP blocked: {type(e).__name__}")
        return False
    except PoTokenRequired as e:
        print(f"[BLOCKED] {label} ({video_id}) -> proof-of-origin token required: {e}")
        return False
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        print(f"[NONE]  {label} ({video_id}) -> no usable transcript: {type(e).__name__}")
        return False
    except Exception as e:
        print(f"[ERROR] {label} ({video_id}) -> {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    results = {label: probe(label, vid) for label, vid in VIDEOS.items()}
    print("\nSUMMARY:", results)
    # Non-zero exit if anything failed, so CI surfaces it as a red build
    raise SystemExit(0 if all(results.values()) else 1)
