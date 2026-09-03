"""
Hybrid retrieval over `document_chunks` (Phase 5): combines MongoDB Atlas
Vector Search (`$vectorSearch` over the `embedding` field, implemented in
Phase 4 -- app/db/chunk_repository.py:vector_search) with Atlas Search
(BM25-style full-text via `$search`, app/db/chunk_repository.py:text_search),
then merges the two ranked lists with reciprocal rank fusion (RRF). See
docs/RAG.md ("Why hybrid retrieval") for the rationale and
app/db/collections.py for the index names.

`resource_types`/`tags`, together with the caller's `user_id` (Phase 8,
always applied -- see `_resolve_resource_ids`), are resolved to a
`resource_id` allowlist up front (via
app/db/resource_repository.py:list_ids_by_filter, the same pattern
app/services/search_service.py already uses) and passed as a native
pre-filter to *both* retrievers. This is also how user isolation is
enforced here: it reuses the `resource_id` field the Atlas indexes already
have marked filterable, rather than requiring a new `user_id` filterable
field on either index.
"""

import asyncio
import logging

from app.config import settings
from app.db import chunk_repository, resource_repository
from app.models.chunk import DocumentChunk
from app.services.rag.embeddings import EmbeddingProvider, EmbeddingProviderError, get_embedding_provider

logger = logging.getLogger(__name__)


class EmbeddingUnavailableError(Exception):
    """The embedding provider couldn't embed the query (bad config, API error)."""


class RetrievalUnavailableError(Exception):
    """Both the vector and keyword retrieval branches failed -- there is
    nothing to retrieve with. A single branch failing does NOT raise this;
    retrieval degrades gracefully to whichever branch succeeded."""


class RetrievalFilters:
    def __init__(
        self,
        user_id: str,
        resource_types: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        self.user_id = user_id
        self.resource_types = resource_types
        self.tags = tags


async def hybrid_search(
    query: str,
    filters: RetrievalFilters,
    top_k: int = 8,
    *,
    embedding_provider: EmbeddingProvider | None = None,
) -> list[DocumentChunk]:
    """Fused chunks in rank order, best first. Thin wrapper around
    `hybrid_search_with_scores` for callers that don't need fusion scores."""
    scored = await hybrid_search_with_scores(
        query, filters, top_k, embedding_provider=embedding_provider
    )
    return [chunk for chunk, _ in scored]


async def hybrid_search_with_scores(
    query: str,
    filters: RetrievalFilters,
    top_k: int = 8,
    *,
    embedding_provider: EmbeddingProvider | None = None,
) -> list[tuple[DocumentChunk, float]]:
    """Same as `hybrid_search` but also returns each chunk's fused RRF
    score, so callers (app/services/rag/pipeline.py) can attach it to a
    Citation without re-deriving fusion internals."""
    resource_ids = await _resolve_resource_ids(filters)
    if not resource_ids:
        # Either a type/tag filter matched no resources, or this user has
        # none at all -- no point calling either retriever for a search
        # that can't match anything.
        return []

    candidate_pool = max(top_k * settings.rag_candidate_multiplier, settings.rag_min_candidate_pool)

    (vector_ranked, vector_scores, vector_error), (text_ranked, text_error) = await asyncio.gather(
        _run_vector_branch(query, candidate_pool, resource_ids, embedding_provider),
        _run_text_branch(query, candidate_pool, resource_ids),
    )

    if vector_error is not None and text_error is not None:
        raise RetrievalUnavailableError(
            "Hybrid retrieval is unavailable: both vector and keyword search failed "
            f"(vector: {vector_error}; keyword: {text_error})."
        )

    fused = _reciprocal_rank_fusion(
        [vector_ranked, text_ranked], k=settings.rag_rrf_k, tiebreak_scores=vector_scores
    )
    top_ids = [chunk_id for chunk_id, _ in fused[:top_k]]
    score_by_id = dict(fused)

    chunks = await chunk_repository.get_many_by_ids(top_ids, filters.user_id)
    chunks_by_id = {chunk.id: chunk for chunk in chunks}
    return [
        (chunks_by_id[chunk_id], score_by_id[chunk_id])
        for chunk_id in top_ids
        if chunk_id in chunks_by_id  # chunk deleted between fusion and this fetch
    ]


async def _resolve_resource_ids(filters: RetrievalFilters) -> list[str]:
    """Always resolved and always user_id-scoped (Phase 8) -- an empty list
    means "this user has nothing matching" (caller short-circuits); it is
    never None/"unrestricted", since that would search across every user's
    chunks."""
    type_matches = filters.resource_types or [None]
    tag_matches = filters.tags or [None]
    matched: set[str] = set()
    for type_filter in type_matches:
        for tag_filter in tag_matches:
            matched.update(
                await resource_repository.list_ids_by_filter(
                    user_id=filters.user_id, type_filter=type_filter, tag_filter=tag_filter
                )
            )
    return list(matched)


async def _run_vector_branch(
    query: str,
    candidate_pool: int,
    resource_ids: list[str] | None,
    embedding_provider: EmbeddingProvider | None,
) -> tuple[list[str], dict[str, float], Exception | None]:
    """Never raises -- a failure is reported via the returned error, so the
    caller can fall back to the surviving branch instead of aborting."""
    try:
        provider = embedding_provider or get_embedding_provider()
        query_vector = await provider.embed_query(query)
    except EmbeddingProviderError as exc:
        logger.warning("Vector retrieval unavailable (query embedding failed): %s", exc)
        return [], {}, EmbeddingUnavailableError(str(exc))

    try:
        hits = await chunk_repository.vector_search(
            query_vector.values, top_k=candidate_pool, resource_ids=resource_ids
        )
    except Exception as exc:  # pymongo OperationFailure, e.g. non-Atlas / missing index
        logger.warning("Vector retrieval unavailable ($vectorSearch failed): %s", exc)
        return [], {}, exc

    ranked_ids = [hit["id"] for hit in hits]
    scores = {hit["id"]: hit["score"] for hit in hits}
    return ranked_ids, scores, None


async def _run_text_branch(
    query: str, candidate_pool: int, resource_ids: list[str] | None
) -> tuple[list[str], Exception | None]:
    """Never raises -- same fallback contract as `_run_vector_branch`."""
    try:
        hits = await chunk_repository.text_search(query, top_k=candidate_pool, resource_ids=resource_ids)
    except Exception as exc:  # pymongo OperationFailure, e.g. index not provisioned
        logger.warning("Keyword retrieval unavailable ($search failed): %s", exc)
        return [], exc
    return [hit["id"] for hit in hits], None


def _reciprocal_rank_fusion(
    ranked_id_lists: list[list[str]],
    *,
    k: int,
    tiebreak_scores: dict[str, float] | None = None,
) -> list[tuple[str, float]]:
    """RRF: fused_score(id) = sum(1 / (k + rank)) over every list it appears
    in (1-based rank; 0 contribution from a list it's absent from). Returns
    every id that appeared in any list, sorted by fused score descending;
    the caller truncates to its own top_k. Ties are broken by
    `tiebreak_scores` (the raw vector cosine score, when available)
    descending, then by chunk id ascending for deterministic output."""
    scores: dict[str, float] = {}
    for ranked_ids in ranked_id_lists:
        for rank, chunk_id in enumerate(ranked_ids, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)

    tiebreak = tiebreak_scores or {}
    return sorted(
        scores.items(),
        key=lambda item: (-item[1], -tiebreak.get(item[0], 0.0), item[0]),
    )
