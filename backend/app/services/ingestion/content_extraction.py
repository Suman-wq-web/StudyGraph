"""
Resolves the raw text to process for a resource, per resource type. This is
the first stage of the pipeline in app/services/processing_service.py:

    resource -> extract_content() -> normalize_text() -> chunk_text() -> document_chunks

Note and Article resources use whatever the user typed/pasted into
`resource.content`.

URL resources are automatically fetched: app/services/processing_service.py
decides which fetcher to use based on the link --

  * a YouTube link uses youtube_transcript.fetch_transcript() (detected via
    youtube_transcript.extract_video_id), exactly like a Video resource
    does -- see below.
  * any other http(s) link uses url_extraction.fetch_url_content()
    (app/services/ingestion/url_extraction.py), which extracts readable
    article text from HTML pages or text from direct PDF URLs.

Either fetch happens *before* this function is called (it needs a network
call, so it can't live here) and its result is passed in as
`url_extracted_text`/`url_extraction_error` (generic URL fetch) or
`video_transcript`/`video_transcript_error` (YouTube fetch, shared with
Video resources). A successful fetch is preferred; if it failed, or there
was no `source_url` to fetch at all, this falls back to manually-provided
`resource.content`, and otherwise surfaces the fetch failure's own clear
error message (or a generic "nothing to use" message when no fetch was
even attempted).

Video resources are automatically transcribed: app/services/ingestion/
youtube_transcript.py fetches the YouTube transcript for `resource.source_url`
*before* this function is called, and its result is passed in as
`video_transcript`/`video_transcript_error`. A successfully fetched
transcript is preferred; if fetching failed, this falls back to
manually-provided `resource.content`, and otherwise surfaces the fetch
failure's own clear error message.

This function itself stays pure and side-effect-free (no network calls) --
so it can be unit tested independently. See
backend/tests/test_content_extraction.py.
"""

from dataclasses import dataclass

from app.models.resource import Resource, ResourceType

_NO_CONTENT_MESSAGE = (
    "No content available. Add text content to this resource before processing."
)
_URL_NO_SOURCE_MESSAGE = (
    "No URL or content available. Add a source URL (so it can be fetched automatically) or "
    "paste the content manually, then process again."
)
_VIDEO_NO_TRANSCRIPT_MESSAGE = (
    "No transcript available for this video, and no transcript was manually provided. "
    "Add a transcript manually via the content field, then process again."
)


@dataclass(frozen=True)
class ExtractionResult:
    """`text` is set on success. `error` is a short, user-safe message on
    failure -- never an internal exception string or stack trace."""

    text: str | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.text is not None


def extract_content(
    resource: Resource,
    *,
    video_transcript: str | None = None,
    video_transcript_error: str | None = None,
    url_extracted_text: str | None = None,
    url_extraction_error: str | None = None,
) -> ExtractionResult:
    if resource.type in (ResourceType.NOTE, ResourceType.ARTICLE):
        return _from_stored_content(resource, _NO_CONTENT_MESSAGE)
    if resource.type == ResourceType.URL:
        if video_transcript and video_transcript.strip():
            return ExtractionResult(text=video_transcript)
        if url_extracted_text and url_extracted_text.strip():
            return ExtractionResult(text=url_extracted_text)
        fetch_error = video_transcript_error or url_extraction_error
        return _from_stored_content(resource, fetch_error or _URL_NO_SOURCE_MESSAGE)
    if resource.type == ResourceType.VIDEO:
        if video_transcript and video_transcript.strip():
            return ExtractionResult(text=video_transcript)
        return _from_stored_content(resource, video_transcript_error or _VIDEO_NO_TRANSCRIPT_MESSAGE)
    return ExtractionResult(text=None, error=f"Unsupported resource type: {resource.type}")


def _from_stored_content(resource: Resource, missing_message: str) -> ExtractionResult:
    if resource.content and resource.content.strip():
        return ExtractionResult(text=resource.content)
    return ExtractionResult(text=None, error=missing_message)
