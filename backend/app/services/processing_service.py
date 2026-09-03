"""
Orchestrates turning a saved resource's text into token-bounded chunks ready
for future embedding:

    resource -> [video, or url pointing at YouTube: youtube_transcript.fetch_transcript()]
             -> [url pointing anywhere else: url_extraction.fetch_url_content()]
             -> content_extraction.extract_content()
             -> normalization.normalize_text()
             -> chunking.chunk_text()
             -> chunk_repository.replace_chunks_for_resource()

A URL resource whose `source_url` is a YouTube link is routed through the
same transcript fetch as a Video resource (detected via
youtube_transcript.extract_video_id). Any other URL resource with a
`source_url` is routed through the generic HTML/PDF fetcher instead
(app/services/ingestion/url_extraction.py). Exactly one of the two fetches
ever runs per resource -- never both.

Routes in app/api/v1/resources.py call into this module; it never touches
Mongo directly (that's app/db/resource_repository.py and
app/db/chunk_repository.py) and never calls tiktoken directly (that's
app/services/ingestion/chunking.py). Processing runs as a FastAPI background
task: the POST endpoint flips the resource to PROCESSING and returns
immediately, and this module does the actual work afterwards, finishing in
READY or FAILED -- see docs/API.md for the resulting request/response shape.
Re-running this (the "Reprocess" action) re-fetches the transcript for Video
resources too, same as it re-resolves content for every other type.
"""

import logging

from app.config import settings
from app.db import chunk_repository, resource_repository
from app.models.resource import Resource, ResourceStatus, ResourceType
from app.services import embedding_service
from app.services.ingestion import chunking
from app.services.ingestion.content_extraction import extract_content
from app.services.ingestion.normalization import normalize_text
from app.services.ingestion.url_extraction import fetch_url_content
from app.services.ingestion.youtube_transcript import extract_video_id, fetch_transcript

logger = logging.getLogger(__name__)


class ResourceNotFoundError(Exception):
    """Raised when the target resource doesn't exist."""


class AlreadyProcessingError(Exception):
    """Raised when a process is requested for a resource already mid-processing."""


async def start_processing(resource_id: str, user_id: str) -> Resource:
    """
    Validates the resource exists (and is owned by `user_id`) and isn't
    already processing, flips it to PROCESSING, and returns that state
    immediately. The caller (the API router) is responsible for scheduling
    `run_processing` as a background task -- this function does not run the
    pipeline itself, so it stays fast and the request doesn't block on
    tokenization/Mongo writes.
    """
    resource = await resource_repository.get_by_id(resource_id, user_id)
    if resource is None:
        raise ResourceNotFoundError(resource_id)
    if resource.status == ResourceStatus.PROCESSING:
        raise AlreadyProcessingError(resource_id)

    processing = await resource_repository.set_processing_state(
        resource_id, status=ResourceStatus.PROCESSING, error=None
    )
    if processing is None:
        raise ResourceNotFoundError(resource_id)
    return processing


async def run_processing(resource_id: str, user_id: str) -> None:
    """The actual pipeline. Scheduled by the router as a background task after
    `start_processing` returns; never raises -- every failure path records a
    FAILED status with a user-safe `processing_error` instead."""
    resource = await resource_repository.get_by_id(resource_id, user_id)
    if resource is None:
        logger.warning("Resource %s was deleted before processing ran", resource_id)
        return

    video_transcript: str | None = None
    video_transcript_error: str | None = None
    url_extracted_text: str | None = None
    url_extraction_error: str | None = None

    is_youtube_url = resource.type == ResourceType.URL and extract_video_id(resource.source_url) is not None
    if resource.type == ResourceType.VIDEO or is_youtube_url:
        transcript_result = await fetch_transcript(resource.source_url)
        if transcript_result.ok:
            video_transcript = transcript_result.text
        else:
            video_transcript_error = transcript_result.error
    elif resource.type == ResourceType.URL and resource.source_url:
        url_result = await fetch_url_content(resource.source_url)
        if url_result.ok:
            url_extracted_text = url_result.text
        else:
            url_extraction_error = url_result.error

    extraction = extract_content(
        resource,
        video_transcript=video_transcript,
        video_transcript_error=video_transcript_error,
        url_extracted_text=url_extracted_text,
        url_extraction_error=url_extraction_error,
    )
    if not extraction.ok:
        await resource_repository.set_processing_state(
            resource_id, status=ResourceStatus.FAILED, error=extraction.error
        )
        return

    assert extraction.text is not None  # ok implies text is set
    normalized = normalize_text(extraction.text)

    try:
        text_chunks = chunking.chunk_text(normalized)
    except ValueError:
        logger.exception("Chunking configuration error for resource %s", resource_id)
        await resource_repository.set_processing_state(
            resource_id,
            status=ResourceStatus.FAILED,
            error="Processing failed due to an internal configuration error.",
        )
        return

    if not text_chunks:
        await resource_repository.set_processing_state(
            resource_id,
            status=ResourceStatus.FAILED,
            error="No chunkable text was found after normalization.",
        )
        return

    await chunk_repository.replace_chunks_for_resource(resource_id, text_chunks, user_id)
    await resource_repository.set_processing_state(resource_id, status=ResourceStatus.READY, error=None)

    if settings.auto_embed_after_processing:
        await _auto_embed(resource_id, user_id)


async def _auto_embed(resource_id: str, user_id: str) -> None:
    """
    Chains straight into embedding_service's own start_embedding/run_embedding
    (Phase 4) right after chunking succeeds, so a newly processed resource
    becomes semantically searchable without a separate manual step. This
    duplicates none of the embedding logic itself -- it only decides *when*
    to call it.

    Never raises, matching run_processing's "never raises" contract: if
    start_embedding can't even begin (e.g. it lost a concurrency race to
    another embed request -- see start_embedding's compare-and-swap), the
    resource simply stays at READY, which is still a valid state the
    "Embed" button can act on. If embedding itself fails, run_embedding
    already records that as FAILED with a user-safe error -- nothing extra
    to do here.
    """
    try:
        await embedding_service.start_embedding(resource_id, user_id)
    except (
        embedding_service.ResourceNotFoundError,
        embedding_service.AlreadyEmbeddingError,
        embedding_service.NotReadyForEmbeddingError,
    ) as exc:
        logger.warning("Skipping automatic embedding for resource %s: %s", resource_id, exc)
        return

    await embedding_service.run_embedding(resource_id)


async def get_processing_status(resource_id: str, user_id: str) -> tuple[Resource, int] | None:
    resource = await resource_repository.get_by_id(resource_id, user_id)
    if resource is None:
        return None
    chunk_count = await chunk_repository.count_by_resource(resource_id)
    return resource, chunk_count
