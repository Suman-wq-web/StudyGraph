"""
Semantic similarity search over `document_chunks` (Phase 4):

    VectorSearchRequest
        -> resolve caller's own resource ids, narrowed by any type/tag
           filter (app/db/resource_repository.py, always user_id-scoped
           since Phase 8)
        -> EmbeddingProvider.embed_query()                    [app/services/rag/embeddings.py]
        -> chunk_repository.vector_search()                    [MongoDB Atlas $vectorSearch]
        -> join resource metadata (title/type) onto each hit
        -> VectorSearchResponse

Read-only retrieval only -- no generated answer, no citations beyond the raw
chunk/resource identifiers returned here. That's Phase 5's RAG chat.
"""

from app.db import chunk_repository, resource_repository
from app.models.embedding import VectorSearchRequest, VectorSearchResponse, VectorSearchResultItem
from app.services.rag.embeddings import EmbeddingProvider, EmbeddingProviderError, get_embedding_provider


class EmbeddingUnavailableError(Exception):
    """The embedding provider couldn't embed the query (bad config, API error)."""


class VectorSearchUnavailableError(Exception):
    """The database doesn't support $vectorSearch (e.g. a local, non-Atlas
    MongoDB) or the Atlas Vector Search index isn't provisioned yet."""


async def vector_search(
    request: VectorSearchRequest, user_id: str, *, provider: EmbeddingProvider | None = None
) -> VectorSearchResponse:
    # Always resolved, never None (Phase 8): a type/tag filter narrows this
    # further, but the caller's own resource ids are the outer bound in
    # every case -- this is what keeps $vectorSearch from ever seeing
    # another user's chunks, reusing the resource_id field the Atlas index
    # already has indexed as filterable (see app/db/collections.py) rather
    # than requiring a new one.
    tag_matches = request.tags or [None]
    matched: set[str] = set()
    for tag in tag_matches:
        matched.update(
            await resource_repository.list_ids_by_filter(
                user_id=user_id,
                type_filter=request.resource_type.value if request.resource_type else None,
                tag_filter=tag,
            )
        )
    resource_ids = list(matched)
    if not resource_ids:
        # No resource matches the filter (or this user has none at all) --
        # no point calling the embedding provider or Atlas for a search
        # that can't match.
        return VectorSearchResponse(query=request.query, results=[], count=0)

    try:
        provider = provider or get_embedding_provider()
        query_vector = await provider.embed_query(request.query)
    except EmbeddingProviderError as exc:
        raise EmbeddingUnavailableError(str(exc)) from exc

    try:
        hits = await chunk_repository.vector_search(
            query_vector.values, top_k=request.top_k, resource_ids=resource_ids
        )
    except Exception as exc:
        # Catches pymongo's OperationFailure for an unsupported/missing
        # $vectorSearch stage (e.g. a local, non-Atlas MongoDB) without
        # importing pymongo error types here just to narrow this one catch --
        # any failure at this call site means "vector search isn't usable
        # right now", which is exactly what this error communicates.
        raise VectorSearchUnavailableError(
            "Vector search is unavailable. This requires a MongoDB Atlas cluster with the "
            "document_chunks_vector_index provisioned -- see docs/DATABASE.md."
        ) from exc

    if not hits:
        return VectorSearchResponse(query=request.query, results=[], count=0)

    resources = {
        resource.id: resource
        for resource in await resource_repository.get_many_by_ids(
            list({hit["resource_id"] for hit in hits}), user_id
        )
    }

    results: list[VectorSearchResultItem] = []
    for hit in hits:
        resource = resources.get(hit["resource_id"])
        if resource is None:
            continue  # resource was deleted between the vector search and this join
        results.append(
            VectorSearchResultItem(
                chunk_id=hit["id"],
                resource_id=hit["resource_id"],
                resource_title=resource.title,
                resource_type=resource.type,
                chunk_index=hit["chunk_index"],
                text=hit["text"],
                score=hit["score"],
            )
        )

    return VectorSearchResponse(query=request.query, results=results, count=len(results))
