"""
transcript_core.py

Core logic for fetching YouTube transcripts, extracted from youtube_transcript.py
so it can be shared between the CLI script and the Flask web app.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)
from youtube_transcript_api.proxies import GenericProxyConfig


def extract_video_id(url_or_id: str) -> str:
    """Accepts a raw video ID or a full YouTube URL and returns the video ID."""
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url_or_id):
        return url_or_id

    patterns = [
        r"(?:v=|/)([A-Za-z0-9_-]{11})(?:[&?/]|$)",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"shorts/([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)

    raise ValueError(f"Could not extract a video ID from: {url_or_id!r}")


def build_api(proxy: str | None) -> YouTubeTranscriptApi:
    """Builds a YouTubeTranscriptApi client, optionally routed through a proxy."""
    if proxy:
        return YouTubeTranscriptApi(
            proxy_config=GenericProxyConfig(http_url=proxy, https_url=proxy)
        )
    return YouTubeTranscriptApi()


def fetch_transcript(video_id: str, languages: list[str], api: YouTubeTranscriptApi):
    """
    Tries to fetch a transcript in the requested languages, in order of
    preference. Falls back to any manually created transcript, then to
    any auto-generated transcript, if none of the preferred languages exist.
    """
    transcript_list = api.list(video_id)

    try:
        fetched = transcript_list.find_transcript(languages).fetch()
        return fetched.to_raw_data()
    except NoTranscriptFound:
        pass

    for t in transcript_list:
        if t.is_translatable:
            for lang in languages:
                for translation in t.translation_languages:
                    if translation["language_code"] == lang:
                        return t.translate(lang).fetch().to_raw_data()

    for t in transcript_list:
        return t.fetch().to_raw_data()

    raise NoTranscriptFound(video_id, languages, transcript_list)


def format_timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_txt(entries) -> str:
    lines = []
    for e in entries:
        minutes, seconds = divmod(int(e["start"]), 60)
        hours, minutes = divmod(minutes, 60)
        stamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        lines.append(f"[{stamp}] {e['text']}")
    return "\n".join(lines)


def to_srt(entries) -> str:
    blocks = []
    for i, e in enumerate(entries, start=1):
        start = format_timestamp(e["start"])
        end = format_timestamp(e["start"] + e.get("duration", 0))
        blocks.append(f"{i}\n{start} --> {end}\n{e['text']}\n")
    return "\n".join(blocks)


def to_plain(entries) -> str:
    return " ".join(e["text"].replace("\n", " ") for e in entries)


def render(entries, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(entries, ensure_ascii=False, indent=2)
    if fmt == "srt":
        return to_srt(entries)
    if fmt == "plain":
        return to_plain(entries)
    return to_txt(entries)


def list_channel_videos(channel_url: str, limit: int | None, proxy: str | None) -> list[dict]:
    """
    Uses yt-dlp to list all videos on a channel without downloading them.
    Returns a list of {"id": ..., "title": ...}.
    """
    url = channel_url.rstrip("/")
    if not url.endswith(("/videos", "/streams", "/shorts")):
        url += "/videos"

    cmd = [sys.executable, "-m", "yt_dlp", "--flat-playlist", "--print", "%(id)s\t%(title)s", url]
    if limit:
        cmd[3:3] = ["--playlist-end", str(limit)]
    if proxy:
        cmd[3:3] = ["--proxy", proxy]

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    )

    videos = []
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        vid, title = line.split("\t", 1)
        videos.append({"id": vid, "title": title})
    return videos
