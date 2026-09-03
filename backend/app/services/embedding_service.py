"""
Orchestrates embedding a resource's chunks (Phase 4):

    resource (status=ready/embedded/failed, chunks exist)
        -> chunk_repository.list_unembedded_by_resource()   [skips already-embedded chunks]
        -> EmbeddingProvider.embed_documents()               [batched, retried on transient errors]
        -> chunk_repository.set_embedding() per chunk
        -> resource_repository.set_processing_state(EMBEDDED | FAILED)

Routes in app/api/v1/resources.py call into this module; it never touches
Mongo directly (app/db/chunk_repository.py, app/db/resource_repository.py)
and never calls the Gemini SDK directly (app/services/rag/embeddings.py).
Runs as a FastAPI background task, the same pattern as
app/services/processing_service.py: POST /embed flips the resource to
EMBEDDING and returns immediately; this module does the actual work
afterwards, finishing in EMBEDDED or FAILED.
"""

import asyncio
import logging

from app.config import settings
from app.db import chunk_repository, resource_repository
from app.models.resource import Resource, ResourceStatus
from app.services.rag.embeddings import (
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingRateLimitError,
    EmbeddingTransientError,
    EmbeddingVector,
    get_embedding_provider,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 1.0
# Cap on honoring Gemini's server-suggested retryDelay (see
# app/services/rag/gemini_retry.py). This retry runs inside a background
# task, but an unbounded wait -- quota errors can suggest very long delays
# -- would still hold the resource in EMBEDDING far longer than a user
# checking back on it would expect.
MAX_RETRY_DELAY_SECONDS = 30.0


class ResourceNotFoundError(Exception):
    """Raised when the target resource doesn't exist."""


class AlreadyEmbeddingError(Exception):
    """Raised when embedding is requested for a resource already mid-embedding."""


class NotReadyForEmbeddingError(Exception):
    """Raised when a resource hasn't been chunked (successfully) yet."""


_EMBEDDABLE_STATUSES = (ResourceStatus.READY, ResourceStatus.EMBEDDED, ResourceStatus.FAILED)


async def start_embedding(resource_id: str, user_id: str) -> Resource:
    """
    Validates the resource has chunks to embed and isn't already embedding,
    flips it to EMBEDDING, and returns that state immediately -- same
    fast/non-blocking split as processing_service.start_processing. Allowed
    from READY, EMBEDDED (re-embed after new chunks were added -- doesn't
    happen today but the check doesn't assume it can't), or FAILED (retry
    after a previous embedding attempt failed partway through).

    The READY/EMBEDDED/FAILED -> EMBEDDING flip is an atomic compare-and-swap
    (resource_repository.set_processing_state's `expected_statuses`), not a
    plain read-then-write: two concurrent calls for the same resource (e.g.
    a manual "Embed" click racing the automatic post-processing embed, or a
    double click) both pass the status check above, but only one of them
    wins the atomic update. The loser sees `None` back and reports it the
    same way it would have if it had observed EMBEDDING in the first place,
    so a resource is never embedded by two overlapping runs at once.
    """
    resource = await resource_repository.get_by_id(resource_id, user_id)
    if resource is None:
        raise ResourceNotFoundError(resource_id)
    if resource.status == ResourceStatus.EMBEDDING:
        raise AlreadyEmbeddingError(resource_id)
    if resource.status not in _EMBEDDABLE_STATUSES:
        raise NotReadyForEmbeddingError(resource_id)

    chunk_count = await chunk_repository.count_by_resource(resource_id)
    if chunk_count == 0:
        raise NotReadyForEmbeddingError(resource_id)

    embedding_state = await resource_repository.set_processing_state(
        resource_id,
        status=ResourceStatus.EMBEDDING,
        error=None,
        expected_statuses=_EMBEDDABLE_STATUSES,
    )
    if embedding_state is None:
        # Either lost the compare-and-swap race to a concurrent
        # start_embedding call, or the resource was deleted in the interim --
        # both are transient/already-in-progress situations from the
        # caller's point of view, not "this resource doesn't exist".
        raise AlreadyEmbeddingError(resource_id)
    return embedding_state


async def run_embedding(resource_id: str, *, provider: EmbeddingProvider | None = None) -> None:
    """The actual pipeline. Scheduled as a background task after
    `start_embedding` returns; never raises -- every failure path records a
    FAILED status with a user-safe `processing_error` instead. `provider` is
    injectable so tests never construct a real GeminiEmbeddingProvider."""
    try:
        provider = provider or get_embedding_provider()
    except EmbeddingProviderError as exc:
        await resource_repository.set_processing_state(
            resource_id, status=ResourceStatus.FAILED, error=str(exc)
        )
        return

    pending_chunks = await chunk_repository.list_unembedded_by_resource(resource_id)
    if not pending_chunks:
        # Idempotent: nothing left to embed (already all done, or the
        # resource has no chunks -- start_embedding already guards the
        # latter, but this stays correct even if called directly).
        await resource_repository.set_processing_state(
            resource_id, status=ResourceStatus.EMBEDDED, error=None
        )
        return

    batch_size = max(1, settings.embedding_batch_size)
    try:
        for i in range(0, len(pending_chunks), batch_size):
            batch = pending_chunks[i : i + batch_size]
            vectors = await _embed_with_retry(provider, [chunk.text for chunk in batch])
            for chunk, vector in zip(batch, vectors):
                await chunk_repository.set_embedding(chunk.id, vector.values)
    except EmbeddingProviderError as exc:
        logger.warning("Embedding failed for resource %s: %s", resource_id, exc)
        await resource_repository.set_processing_state(
            resource_id, status=ResourceStatus.FAILED, error=_user_safe_message(exc)
        )
        return
    except Exception:
        logger.exception("Unexpected error embedding resource %s", resource_id)
        await resource_repository.set_processing_state(
            resource_id,
            status=ResourceStatus.FAILED,
            error="Embedding failed due to an unexpected error.",
        )
        return

    await resource_repository.set_processing_state(resource_id, status=ResourceStatus.EMBEDDED, error=None)


async def _embed_with_retry(provider: EmbeddingProvider, texts: list[str]) -> list[EmbeddingVector]:
    """Retries rate-limit/transient failures. When the failure is a 429 that
    carried Gemini's own suggested `retry_delay_seconds`, that's honored
    (capped at MAX_RETRY_DELAY_SECONDS) instead of guessing -- otherwise
    falls back to the previous fixed exponential backoff. Non-retryable
    errors (bad request, auth) propagate immediately."""
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            return await provider.embed_documents(texts)
        except (EmbeddingRateLimitError, EmbeddingTransientError) as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(_backoff_seconds(attempt, exc))
    raise EmbeddingProviderError(
        f"Embedding provider unavailable after {MAX_ATTEMPTS} attempts: {last_error}"
    ) from last_error


def _backoff_seconds(attempt: int, exc: Exception) -> float:
    """`exc` is an EmbeddingRateLimitError/EmbeddingTransientError; only the
    former ever carries `retry_delay_seconds` (Gemini's RetryInfo detail is
    429-specific), so a plain `getattr` naturally falls back to exponential
    backoff for transient (5xx) failures too."""
    retry_delay_seconds = getattr(exc, "retry_delay_seconds", None)
    if retry_delay_seconds is not None:
        return min(max(retry_delay_seconds, 0.0), MAX_RETRY_DELAY_SECONDS)
    return BASE_BACKOFF_SECONDS * (2**attempt)


def _user_safe_message(exc: EmbeddingProviderError) -> str:
    # Messages raised by app/services/rag/embeddings.py are already written
    # to be user-safe (no keys, no raw stack traces) -- this seam exists so
    # that stays a deliberate choice if the error source ever changes.
    return str(exc) or "Embedding failed."


async def get_embedding_status(resource_id: str, user_id: str) -> tuple[Resource, int, int] | None:
    """Returns (resource, embedded_chunk_count, total_chunk_count)."""
    resource = await resource_repository.get_by_id(resource_id, user_id)
    if resource is None:
        return None
    total = await chunk_repository.count_by_resource(resource_id)
    embedded = await chunk_repository.count_embedded_by_resource(resource_id)
    return resource, embedded, total
