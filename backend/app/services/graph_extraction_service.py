"""
Orchestrates concept/relationship extraction for a resource's chunks
(Phase 6):

    resource (chunks exist)
        -> chunk_repository.list_unextracted_by_resource()  [skips
           already-extracted chunks]
        -> extraction.extract_from_chunk()                   [one Gemini
           call per chunk, via the existing, unmodified
           GenerationProvider -- see app/services/ingestion/extraction.py]
        -> concept_repository / edge_repository upserts        [resolve by
           normalized name, idempotent]
        -> chunk_repository.set_concepts_extracted() per chunk

Routes in app/api/v1/resources.py call into this module. Unlike
processing_service.py/embedding_service.py, there is no resource-level
status field to flip: extraction progress is entirely visible via
GET /{id}/extraction-status's chunk counts, and a chunk whose response never
parses is simply left unextracted (picked up again by the next /extract
call) rather than recorded against Resource.status, which Phase 3/4 already
use for a different lifecycle. See docs/KNOWLEDGE_GRAPH.md for the full
rationale. Runs as a FastAPI background task, the same pattern as the other
two pipelines.
"""

import asyncio
import logging

from app.db import chunk_repository, concept_repository, edge_repository, resource_repository
from app.models.chunk import DocumentChunk
from app.models.edge import RelationType
from app.models.resource import Resource
from app.services.ingestion import extraction
from app.services.ingestion.extraction import (
    ChunkExtractionResult,
    ExtractedConcept,
    ExtractionParseError,
)
from app.services.rag.generation import (
    GenerationProvider,
    GenerationProviderError,
    GenerationRateLimitError,
    GenerationTransientError,
    get_generation_provider,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 1.0


class ResourceNotFoundError(Exception):
    """Raised when the target resource doesn't exist."""


class NoChunksToExtractError(Exception):
    """Raised when a resource has no chunks yet -- process it first."""


async def start_extraction(resource_id: str, user_id: str) -> int:
    """
    Validates the resource exists (owned by `user_id`) and has chunks, and
    returns how many are currently unextracted. Unlike processing/embedding,
    there is no in-progress guard: extraction's upserts are idempotent by
    (normalized concept name) and (source, target, relation_type), so a
    duplicate trigger wastes some Gemini calls but cannot corrupt stored
    data.
    """
    resource = await resource_repository.get_by_id(resource_id, user_id)
    if resource is None:
        raise ResourceNotFoundError(resource_id)

    total_chunks = await chunk_repository.count_by_resource(resource_id)
    if total_chunks == 0:
        raise NoChunksToExtractError(resource_id)

    pending = await chunk_repository.list_unextracted_by_resource(resource_id)
    return len(pending)


async def run_extraction(
    resource_id: str, user_id: str, *, provider: GenerationProvider | None = None
) -> None:
    """
    The actual pipeline. Scheduled as a background task after
    `start_extraction` returns. Never raises: a misconfigured/unavailable
    provider aborts the whole run (logged -- there's no resource-level field
    to record it against); one chunk's unparseable response is logged and
    skipped, and the loop continues with the rest.
    """
    resource = await resource_repository.get_by_id(resource_id, user_id)
    if resource is None:
        logger.warning("Resource %s was deleted before extraction ran", resource_id)
        return

    try:
        provider = provider or get_generation_provider()
    except GenerationProviderError as exc:
        logger.warning("Concept extraction unavailable for resource %s: %s", resource_id, exc)
        return

    pending_chunks = await chunk_repository.list_unextracted_by_resource(resource_id)

    for chunk in pending_chunks:
        try:
            result = await _extract_with_retry(provider, chunk)
        except ExtractionParseError as exc:
            logger.warning("Skipping chunk %s: %s", chunk.id, exc)
            continue
        except GenerationProviderError as exc:
            logger.warning("Aborting extraction for resource %s: %s", resource_id, exc)
            return

        await _store_extraction(user_id, resource_id, chunk, result)
        await chunk_repository.set_concepts_extracted(chunk.id)


async def get_extraction_status(resource_id: str, user_id: str) -> tuple[Resource, int, int] | None:
    """Returns (resource, extracted_chunk_count, total_chunk_count)."""
    resource = await resource_repository.get_by_id(resource_id, user_id)
    if resource is None:
        return None
    total = await chunk_repository.count_by_resource(resource_id)
    extracted = await chunk_repository.count_extracted_by_resource(resource_id)
    return resource, extracted, total


async def _extract_with_retry(
    provider: GenerationProvider, chunk: DocumentChunk
) -> ChunkExtractionResult:
    """Retries rate-limit/transient failures with exponential backoff, the
    same shape as embedding_service._embed_with_retry.
    `ExtractionParseError` is not retried here -- extraction.extract_from_chunk
    already retries a malformed response once internally."""
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            return await extraction.extract_from_chunk(chunk, provider=provider)
        except (GenerationRateLimitError, GenerationTransientError) as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(BASE_BACKOFF_SECONDS * (2**attempt))
    raise GenerationProviderError(
        f"Generation provider unavailable after {MAX_ATTEMPTS} attempts: {last_error}"
    ) from last_error


async def _store_extraction(
    user_id: str, resource_id: str, chunk: DocumentChunk, result: ChunkExtractionResult
) -> None:
    resolved: dict[str, str] = {}  # normalized name -> concept id, this chunk only
    for concept in result.concepts:
        concept_id = await _resolve_concept(user_id, resource_id, concept)
        resolved[_normalize(concept.name)] = concept_id

    for relation in result.relations:
        source_id = await _resolve_existing(user_id, resolved, relation.source)
        target_id = await _resolve_existing(user_id, resolved, relation.target)
        if source_id is None or target_id is None or source_id == target_id:
            continue
        try:
            relation_type = RelationType(relation.relation_type)
        except ValueError:
            continue
        await _upsert_edge(user_id, source_id, target_id, relation_type, chunk.id)


async def _resolve_concept(user_id: str, resource_id: str, concept: ExtractedConcept) -> str:
    """Resolution/dedupe: exact normalized-name match against the user's
    existing concepts first; only a miss creates a new one. Embedding-
    similarity dedupe is a later refinement (docs/KNOWLEDGE_GRAPH.md), not
    implemented here."""
    normalized = _normalize(concept.name)
    existing = await concept_repository.find_by_normalized_name(user_id, normalized)
    if existing is not None:
        updated = await concept_repository.add_source_resource(existing.id, resource_id)
        return (updated or existing).id
    created = await concept_repository.create(
        user_id=user_id,
        name=concept.name,
        normalized_name=normalized,
        description=concept.description,
        source_resource_id=resource_id,
    )
    return created.id


async def _resolve_existing(user_id: str, resolved: dict[str, str], name: str) -> str | None:
    """Resolves a relationship endpoint to a concept id -- first against
    this chunk's own freshly-extracted concepts, then against the user's
    stored concepts. Returns None (relationship dropped) if neither has it,
    e.g. the model referenced a name it didn't also list in `concepts`."""
    normalized = _normalize(name)
    if normalized in resolved:
        return resolved[normalized]
    existing = await concept_repository.find_by_normalized_name(user_id, normalized)
    if existing is None:
        return None
    resolved[normalized] = existing.id
    return existing.id


async def _upsert_edge(
    user_id: str, source_id: str, target_id: str, relation_type: RelationType, chunk_id: str
) -> None:
    existing = await edge_repository.find_by_triple(user_id, source_id, target_id, relation_type)
    if existing is not None:
        await edge_repository.add_evidence(existing.id, chunk_id)
        return
    await edge_repository.create(
        user_id=user_id,
        source_concept_id=source_id,
        target_concept_id=target_id,
        relation_type=relation_type,
        evidence_chunk_id=chunk_id,
    )


def _normalize(name: str) -> str:
    return " ".join(name.strip().lower().split())
