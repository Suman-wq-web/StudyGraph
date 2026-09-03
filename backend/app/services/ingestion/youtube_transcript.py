"""
Fetches a YouTube video's transcript/captions for use as a Video resource's
content -- the step specific to `ResourceType.VIDEO` that runs just before
the shared pipeline in app/services/processing_service.py:

    resource -> youtube_transcript.fetch_transcript(resource.source_url)
             -> content_extraction.extract_content(resource, video_transcript=...)
             -> normalize_text() -> chunk_text() -> document_chunks

Wraps the third-party `youtube_transcript_api` package behind a small
dataclass result, mirroring content_extraction.ExtractionResult: `text` is
set on success, `error` is a short, user-safe message on failure. The
library itself is synchronous (it uses `requests`), so the actual fetch
runs in a worker thread via `asyncio.to_thread` rather than blocking the
event loop. Every known failure mode (invalid/non-YouTube URL, transcripts
disabled, no transcript available, video unavailable/blocked, ...) is
caught here and turned into `error` -- `fetch_transcript` never raises --
so the caller can always fall back to any manually-provided
`resource.content` instead of failing outright. See
backend/tests/test_youtube_transcript.py.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import CouldNotRetrieveTranscript, NoTranscriptFound, YouTubeTranscriptApi

logger = logging.getLogger(__name__)

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {"youtube.com", "youtu.be", "youtube-nocookie.com"}
_PREFERRED_LANGUAGES = ("en", "en-US", "en-GB")

_NOT_YOUTUBE_MESSAGE = (
    "This URL is not a recognized YouTube video link, so a transcript could not be "
    "fetched automatically."
)
_UNAVAILABLE_MESSAGE = (
    "A transcript is not available for this video (captions may be disabled, or the "
    "video may be unavailable)."
)
_EMPTY_MESSAGE = "This video's transcript came back empty."
_UNEXPECTED_MESSAGE = "An unexpected error occurred while fetching the video transcript."


@dataclass(frozen=True)
class TranscriptResult:
    """`text` is set on success. `error` is a short, user-safe message on
    failure -- never an internal exception string or stack trace."""

    text: str | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.text is not None


def extract_video_id(url: str | None) -> str | None:
    """
    Pulls an 11-character YouTube video ID out of any of the URL shapes
    YouTube actually uses (`watch?v=`, `/shorts/`, `/embed/`, `/live/`,
    `youtu.be/`), with or without extra query params like `&t=`/`&list=`.
    Returns None for a URL that isn't a recognizable YouTube video link.
    Pure, no network call, so it's unit-testable on its own.
    """
    if not url:
        return None

    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[len("www.") :]
    if host.startswith("m."):
        host = host[len("m.") :]
    if host not in _YOUTUBE_HOSTS:
        return None

    candidate: str | None = None
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0] or None
    else:
        query_id = parse_qs(parsed.query).get("v", [None])[0]
        if query_id:
            candidate = query_id
        else:
            for prefix in ("/embed/", "/shorts/", "/live/"):
                if parsed.path.startswith(prefix):
                    candidate = parsed.path[len(prefix) :].split("/")[0]
                    break

    if candidate and _VIDEO_ID_RE.match(candidate):
        return candidate
    return None


async def fetch_transcript(source_url: str | None) -> TranscriptResult:
    """
    Resolves `source_url` to a YouTube video ID and fetches its transcript.
    Never raises -- every failure becomes a clear `TranscriptResult.error`.
    """
    video_id = extract_video_id(source_url)
    if video_id is None:
        return TranscriptResult(text=None, error=_NOT_YOUTUBE_MESSAGE)

    try:
        return await asyncio.to_thread(_fetch_transcript_sync, video_id)
    except Exception:
        logger.exception("Unexpected error fetching YouTube transcript for video %s", video_id)
        return TranscriptResult(text=None, error=_UNEXPECTED_MESSAGE)


def _fetch_transcript_sync(video_id: str) -> TranscriptResult:
    """The actual (blocking, network-bound) fetch -- always called via
    `asyncio.to_thread`, never directly from async code."""
    api = YouTubeTranscriptApi()
    try:
        transcript_list = api.list(video_id)
        try:
            transcript = transcript_list.find_transcript(_PREFERRED_LANGUAGES)
        except NoTranscriptFound:
            transcript = next(iter(transcript_list), None)
            if transcript is None:
                raise
        fetched = transcript.fetch()
    except CouldNotRetrieveTranscript as exc:
        logger.info("YouTube transcript unavailable for video %s: %s", video_id, exc)
        return TranscriptResult(text=None, error=_UNAVAILABLE_MESSAGE)

    text = " ".join(snippet.text.strip() for snippet in fetched if snippet.text.strip())
    if not text.strip():
        return TranscriptResult(text=None, error=_EMPTY_MESSAGE)
    return TranscriptResult(text=text)
