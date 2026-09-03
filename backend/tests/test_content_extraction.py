from datetime import datetime, timezone

import pytest

from app.models.resource import Resource, ResourceStatus, ResourceType
from app.services.ingestion.content_extraction import extract_content


def _resource(type_: ResourceType, content: str | None) -> Resource:
    now = datetime.now(timezone.utc)
    return Resource(
        id="000000000000000000000000",
        user_id="u1",
        title="Test resource",
        type=type_,
        source_url=None,
        content=content,
        tags=[],
        status=ResourceStatus.PENDING,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.parametrize("resource_type", [ResourceType.NOTE, ResourceType.ARTICLE])
def test_note_and_article_use_stored_content(resource_type):
    resource = _resource(resource_type, "Some real content.")
    result = extract_content(resource)
    assert result.ok
    assert result.text == "Some real content."
    assert result.error is None


@pytest.mark.parametrize("resource_type", [ResourceType.NOTE, ResourceType.ARTICLE])
def test_note_and_article_without_content_fail_clearly(resource_type):
    resource = _resource(resource_type, None)
    result = extract_content(resource)
    assert not result.ok
    assert result.text is None
    assert "content" in result.error.lower()


def test_url_without_source_or_content_reports_clear_error():
    resource = _resource(ResourceType.URL, None)
    result = extract_content(resource)
    assert not result.ok
    assert "url" in result.error.lower() or "content" in result.error.lower()


def test_url_with_manually_provided_content_succeeds():
    resource = _resource(ResourceType.URL, "Manually pasted article text.")
    result = extract_content(resource)
    assert result.ok
    assert result.text == "Manually pasted article text."


def test_url_with_fetched_youtube_transcript_succeeds():
    resource = _resource(ResourceType.URL, None)
    result = extract_content(resource, video_transcript="Automatically fetched transcript text.")
    assert result.ok
    assert result.text == "Automatically fetched transcript text."


def test_url_fetched_transcript_takes_priority_over_stored_content():
    resource = _resource(ResourceType.URL, "Stale manually pasted content.")
    result = extract_content(resource, video_transcript="Fresh automatically fetched transcript.")
    assert result.ok
    assert result.text == "Fresh automatically fetched transcript."


def test_url_falls_back_to_manual_content_when_youtube_transcript_fetch_failed():
    resource = _resource(ResourceType.URL, "Manually pasted content.")
    result = extract_content(
        resource, video_transcript=None, video_transcript_error="Transcripts are disabled for this video."
    )
    assert result.ok
    assert result.text == "Manually pasted content."


def test_url_surfaces_youtube_fetch_error_when_no_manual_content_available():
    resource = _resource(ResourceType.URL, None)
    result = extract_content(
        resource, video_transcript=None, video_transcript_error="Transcripts are disabled for this video."
    )
    assert not result.ok
    assert result.error == "Transcripts are disabled for this video."


def test_url_with_fetched_generic_page_text_succeeds():
    resource = _resource(ResourceType.URL, None)
    result = extract_content(resource, url_extracted_text="Automatically extracted webpage text.")
    assert result.ok
    assert result.text == "Automatically extracted webpage text."


def test_url_fetched_generic_page_text_takes_priority_over_stored_content():
    resource = _resource(ResourceType.URL, "Stale manually pasted content.")
    result = extract_content(resource, url_extracted_text="Fresh automatically extracted webpage text.")
    assert result.ok
    assert result.text == "Fresh automatically extracted webpage text."


def test_url_falls_back_to_manual_content_when_generic_extraction_failed():
    resource = _resource(ResourceType.URL, "Manually pasted content.")
    result = extract_content(
        resource, url_extracted_text=None, url_extraction_error="No readable article text was found."
    )
    assert result.ok
    assert result.text == "Manually pasted content."


def test_url_surfaces_generic_extraction_error_when_no_manual_content_available():
    resource = _resource(ResourceType.URL, None)
    result = extract_content(
        resource, url_extracted_text=None, url_extraction_error="No readable article text was found."
    )
    assert not result.ok
    assert result.error == "No readable article text was found."


def test_video_without_content_or_transcript_reports_clear_error():
    resource = _resource(ResourceType.VIDEO, None)
    result = extract_content(resource)
    assert not result.ok
    assert "transcript" in result.error.lower()


def test_video_with_manually_provided_transcript_succeeds():
    resource = _resource(ResourceType.VIDEO, "Manually pasted transcript.")
    result = extract_content(resource)
    assert result.ok
    assert result.text == "Manually pasted transcript."


def test_video_with_fetched_transcript_succeeds():
    resource = _resource(ResourceType.VIDEO, None)
    result = extract_content(resource, video_transcript="Automatically fetched transcript text.")
    assert result.ok
    assert result.text == "Automatically fetched transcript text."


def test_video_fetched_transcript_takes_priority_over_stored_content():
    resource = _resource(ResourceType.VIDEO, "Stale manually pasted transcript.")
    result = extract_content(resource, video_transcript="Fresh automatically fetched transcript.")
    assert result.ok
    assert result.text == "Fresh automatically fetched transcript."


def test_video_falls_back_to_manual_content_when_transcript_fetch_failed():
    resource = _resource(ResourceType.VIDEO, "Manually pasted transcript.")
    result = extract_content(
        resource, video_transcript=None, video_transcript_error="Transcripts are disabled for this video."
    )
    assert result.ok
    assert result.text == "Manually pasted transcript."


def test_video_surfaces_fetch_error_when_no_manual_content_available():
    resource = _resource(ResourceType.VIDEO, None)
    result = extract_content(
        resource, video_transcript=None, video_transcript_error="Transcripts are disabled for this video."
    )
    assert not result.ok
    assert result.error == "Transcripts are disabled for this video."


def test_whitespace_only_content_is_treated_as_missing():
    resource = _resource(ResourceType.NOTE, "   \n\t  ")
    result = extract_content(resource)
    assert not result.ok
