"""
Tests for app/services/ingestion/youtube_transcript.py: the pure video-ID
parser and the transcript fetcher, the latter tested with a fake
`YouTubeTranscriptApi` (monkeypatched in) so no real network call is ever
made.
"""

import asyncio

import pytest
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, VideoUnavailable

from app.services.ingestion import youtube_transcript as yt


class TestExtractVideoId:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&list=PLxyz",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ?t=10",
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "https://www.youtube.com/live/dQw4w9WgXcQ",
            "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
        ],
    )
    def test_recognized_youtube_urls_yield_the_video_id(self, url):
        assert yt.extract_video_id(url) == "dQw4w9WgXcQ"

    @pytest.mark.parametrize(
        "url",
        [
            None,
            "",
            "https://example.com/watch?v=dQw4w9WgXcQ",
            "https://vimeo.com/12345",
            "not a url at all",
            "https://www.youtube.com/watch?v=short",
            "https://www.youtube.com/channel/UCxyz",
        ],
    )
    def test_non_youtube_or_unparseable_urls_yield_none(self, url):
        assert yt.extract_video_id(url) is None


class _FakeSnippet:
    def __init__(self, text: str):
        self.text = text


class _FakeTranscript:
    def __init__(self, snippets: list[str]):
        self._snippets = snippets

    def fetch(self):
        return [_FakeSnippet(text) for text in self._snippets]


class _FakeTranscriptList:
    def __init__(self, *, transcripts: dict[str, _FakeTranscript] | None = None, video_id: str = "abc"):
        self._transcripts = transcripts or {}
        self._video_id = video_id

    def find_transcript(self, language_codes):
        for code in language_codes:
            if code in self._transcripts:
                return self._transcripts[code]
        raise NoTranscriptFound(self._video_id, language_codes, self)

    def __iter__(self):
        return iter(self._transcripts.values())


class _FakeApi:
    """Stands in for `YouTubeTranscriptApi`. `outcome` is either a
    `_FakeTranscriptList` (success path) or an exception instance/class to
    raise from `.list()`."""

    def __init__(self, outcome):
        self._outcome = outcome

    def list(self, video_id):
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def _run(coro):
    return asyncio.run(coro)


class TestFetchTranscript:
    def test_non_youtube_url_fails_without_calling_the_api(self, monkeypatch):
        def _fail_if_called():
            raise AssertionError("YouTubeTranscriptApi should not be called for a non-YouTube URL")

        monkeypatch.setattr(yt, "YouTubeTranscriptApi", _fail_if_called)
        result = _run(yt.fetch_transcript("https://example.com/watch?v=abc"))
        assert not result.ok
        assert "not a recognized youtube" in result.error.lower()

    def test_english_transcript_is_preferred_and_joined(self, monkeypatch):
        transcript_list = _FakeTranscriptList(
            transcripts={"en": _FakeTranscript(["Hello", "world."])}
        )
        monkeypatch.setattr(yt, "YouTubeTranscriptApi", lambda: _FakeApi(transcript_list))

        result = _run(yt.fetch_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        assert result.ok
        assert result.text == "Hello world."
        assert result.error is None

    def test_falls_back_to_any_available_language_when_english_missing(self, monkeypatch):
        transcript_list = _FakeTranscriptList(transcripts={"de": _FakeTranscript(["Hallo Welt."])})
        monkeypatch.setattr(yt, "YouTubeTranscriptApi", lambda: _FakeApi(transcript_list))

        result = _run(yt.fetch_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        assert result.ok
        assert result.text == "Hallo Welt."

    def test_transcripts_disabled_fails_clearly(self, monkeypatch):
        monkeypatch.setattr(
            yt, "YouTubeTranscriptApi", lambda: _FakeApi(TranscriptsDisabled("dQw4w9WgXcQ"))
        )
        result = _run(yt.fetch_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        assert not result.ok
        assert "transcript" in result.error.lower()
        assert "not available" in result.error.lower()

    def test_video_unavailable_fails_clearly(self, monkeypatch):
        monkeypatch.setattr(
            yt, "YouTubeTranscriptApi", lambda: _FakeApi(VideoUnavailable("dQw4w9WgXcQ"))
        )
        result = _run(yt.fetch_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        assert not result.ok
        assert result.error

    def test_no_transcripts_at_all_fails_clearly(self, monkeypatch):
        empty_list = _FakeTranscriptList(transcripts={})
        monkeypatch.setattr(yt, "YouTubeTranscriptApi", lambda: _FakeApi(empty_list))

        result = _run(yt.fetch_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        assert not result.ok
        assert result.error

    def test_unexpected_error_is_caught_and_reported_generically(self, monkeypatch):
        def _raise_api():
            raise RuntimeError("boom")

        monkeypatch.setattr(yt, "YouTubeTranscriptApi", _raise_api)
        result = _run(yt.fetch_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        assert not result.ok
        assert "unexpected error" in result.error.lower()

    def test_blank_only_snippets_are_reported_as_empty_transcript(self, monkeypatch):
        transcript_list = _FakeTranscriptList(transcripts={"en": _FakeTranscript(["   ", ""])})
        monkeypatch.setattr(yt, "YouTubeTranscriptApi", lambda: _FakeApi(transcript_list))

        result = _run(yt.fetch_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        assert not result.ok
        assert "empty" in result.error.lower()
