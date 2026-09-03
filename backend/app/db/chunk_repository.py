"""
Persistence for the `document_chunks` collection. Mirrors the
resource_repository.py pattern: the only module that turns TextChunk/
DocumentChunk data into Mongo documents and back -- processing_service.py
calls into this rather than touching app/db/mongodb.get_database() directly.
"""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from app.db import mongodb
from app.db.collections import (
    ATLAS_SEARCH_INDEX_FIELD,
    ATLAS_SEARCH_INDEX_NAME,
    ATLAS_VECTOR_INDEX_FIELD,
    ATLAS_VECTOR_INDEX_NAME,
    DOCUMENT_CHUNKS,
)
from app.models.chunk import DocumentChunk
from app.services.ingestion.chunking import TextChunk


def _get_collection():
    return mongodb.get_database()[DOCUMENT_CHUNKS]


def _to_object_id(chunk_id: str) -> ObjectId | None:
    try:
        return ObjectId(chunk_id)
    except (InvalidId, TypeError):
        return None


def _doc_to_chunk(doc: dict[str, Any]) -> DocumentChunk:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return DocumentChunk.model_validate(doc)


async def replace_chunks_for_resource(
    resource_id: str, chunks: list[TextChunk], user_id: str
) -> list[DocumentChunk]:
    """
    Idempotent write for (re)processing: deletes any chunks already stored
    for this resource, then inserts the new set. Running this twice with the
    same input leaves the same chunks in place rather than accumulating
    duplicates. `user_id` (Phase 8) is denormalized from the parent resource
    onto every chunk -- the caller (processing_service.py) has already
    ownership-checked resource_id via a user_id-scoped
    resource_repository.get_by_id() before calling this.
    """
    collection = _get_collection()
    await collection.delete_many({"resource_id": resource_id})

    if not chunks:
        return []

    now = datetime.now(timezone.utc)
    docs: list[dict[str, Any]] = [
        {
            "resource_id": resource_id,
            "user_id": user_id,
            "chunk_index": index,
            "text": chunk.text,
            "token_count": chunk.token_count,
            "start_token": chunk.start_token,
            "end_token": chunk.end_token,
            "metadata": {},
            "embedding": None,
            "concepts_extracted": False,
            "created_at": now,
            "updated_at": now,
        }
        for index, chunk in enumerate(chunks)
    ]
    result = await collection.insert_many(docs)
    for doc, inserted_id in zip(docs, result.inserted_ids):
        doc["_id"] = inserted_id
    return [_doc_to_chunk(doc) for doc in docs]


async def list_by_resource(resource_id: str) -> list[DocumentChunk]:
    cursor = _get_collection().find({"resource_id": resource_id}).sort("chunk_index", 1)
    docs = await cursor.to_list(length=None)
    return [_doc_to_chunk(doc) for doc in docs]


async def count_by_resource(resource_id: str) -> int:
    return await _get_collection().count_documents({"resource_id": resource_id})


async def delete_by_resource(resource_id: str) -> int:
    result = await _get_collection().delete_many({"resource_id": resource_id})
    return result.deleted_count


async def list_unembedded_by_resource(resource_id: str) -> list[DocumentChunk]:
    """Chunks still needing an embedding -- `embedding is None` is the whole
    signal (Phase 3 never writes a fake one). Used by the embedding pipeline
    to skip chunks that already have a real vector, so re-running embedding
    for a resource doesn't re-call the provider for unchanged chunks."""
    cursor = (
        _get_collection().find({"resource_id": resource_id, "embedding": None}).sort("chunk_index", 1)
    )
    docs = await cursor.to_list(length=None)
    return [_doc_to_chunk(doc) for doc in docs]


async def set_embedding(chunk_id: str, embedding: list[float]) -> DocumentChunk | None:
    """Writes one chunk's embedding. Only ever called with a complete, valid
    vector (see app/services/rag/embeddings.py) -- never a partial one."""
    object_id = _to_object_id(chunk_id)
    if object_id is None:
        return None
    doc = await _get_collection().find_one_and_update(
        {"_id": object_id},
        {"$set": {"embedding": embedding, "updated_at": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        return None
    return _doc_to_chunk(doc)


async def count_embedded_by_resource(resource_id: str) -> int:
    return await _get_collection().count_documents(
        {"resource_id": resource_id, "embedding": {"$ne": None}}
    )


async def list_unextracted_by_resource(resource_id: str) -> list[DocumentChunk]:
    """Chunks still needing a concept-extraction pass (Phase 6) --
    `concepts_extracted` not `True` is the whole signal, matching
    `list_unembedded_by_resource`'s null-check idempotency pattern. `$ne`
    (not a plain `False` match) so chunks written before this field existed
    -- which have no `concepts_extracted` key at all -- are still picked up."""
    cursor = (
        _get_collection()
        .find({"resource_id": resource_id, "concepts_extracted": {"$ne": True}})
        .sort("chunk_index", 1)
    )
    docs = await cursor.to_list(length=None)
    return [_doc_to_chunk(doc) for doc in docs]


async def set_concepts_extracted(chunk_id: str) -> DocumentChunk | None:
    """Marks one chunk as extracted -- called once extraction has been
    attempted for it, whether or not any concepts/relationships were found
    (an empty result is still a completed pass, not a failure)."""
    object_id = _to_object_id(chunk_id)
    if object_id is None:
        return None
    doc = await _get_collection().find_one_and_update(
        {"_id": object_id},
        {"$set": {"concepts_extracted": True, "updated_at": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        return None
    return _doc_to_chunk(doc)


async def count_extracted_by_resource(resource_id: str) -> int:
    return await _get_collection().count_documents(
        {"resource_id": resource_id, "concepts_extracted": True}
    )


async def vector_search(
    query_vector: list[float],
    *,
    top_k: int = 5,
    resource_ids: list[str] | None = None,
    num_candidates: int | None = None,
) -> list[dict[str, Any]]:
    """
    Runs MongoDB **Atlas** Vector Search (`$vectorSearch`) against the
    `document_chunks_vector_index` (see app/db/collections.py). This requires
    a MongoDB Atlas cluster with that index actually provisioned -- see
    docs/DATABASE.md ("Atlas Vector Search setup"). Deliberately does **not**
    fall back to computing cosine similarity in Python if `$vectorSearch`
    isn't supported (e.g. a local `mongod`); that would silently diverge from
    what production actually runs. Against a non-Atlas deployment, Mongo
    itself raises an OperationFailure for the unrecognized aggregation
    stage -- callers (app/services/search_service.py) catch that and report
    it clearly rather than returning fabricated results.

    `resource_ids`, when given, pre-filters to those resources via a native
    Atlas filter on the indexed `resource_id` field (see
    ATLAS_VECTOR_INDEX_FILTER_FIELDS in collections.py) -- this is how
    resource type/tag filtering (resolved to resource ids by the caller) is
    applied without denormalizing resource metadata onto every chunk.
    """
    vector_search_stage: dict[str, Any] = {
        "index": ATLAS_VECTOR_INDEX_NAME,
        "path": ATLAS_VECTOR_INDEX_FIELD,
        "queryVector": query_vector,
        "numCandidates": num_candidates or max(top_k * 10, 100),
        "limit": top_k,
    }
    if resource_ids is not None:
        vector_search_stage["filter"] = {"resource_id": {"$in": resource_ids}}

    pipeline = [
        {"$vectorSearch": vector_search_stage},
        {
            "$project": {
                "resource_id": 1,
                "chunk_index": 1,
                "text": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    cursor = _get_collection().aggregate(pipeline)
    docs = await cursor.to_list(length=top_k)
    for doc in docs:
        doc["id"] = str(doc.pop("_id"))
    return docs


async def text_search(
    query: str,
    *,
    top_k: int = 5,
    resource_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Runs MongoDB **Atlas Search** (`$search`, the `text` operator) against
    the `document_chunks_text_search` index -- the BM25-style keyword half
    of hybrid retrieval (see app/services/rag/retrieval.py), fused with
    vector_search() above. Same non-Atlas-fallback stance as vector_search:
    there is deliberately no Python-side keyword-matching approximation --
    an unsupported/missing index surfaces as pymongo's OperationFailure and
    propagates to the caller, which decides what "this side is unavailable"
    means for the fused result.

    `resource_ids`, when given, pre-filters via a native `filter` clause on
    the indexed `resource_id` field -- mirrors vector_search()'s resource_id
    pre-filter so both retrievers apply metadata filters identically.
    """
    compound: dict[str, Any] = {
        "must": [{"text": {"query": query, "path": ATLAS_SEARCH_INDEX_FIELD}}]
    }
    if resource_ids is not None:
        compound["filter"] = [{"in": {"path": "resource_id", "value": resource_ids}}]

    pipeline = [
        {"$search": {"index": ATLAS_SEARCH_INDEX_NAME, "compound": compound}},
        {"$limit": top_k},
        {
            "$project": {
                "resource_id": 1,
                "chunk_index": 1,
                "text": 1,
                "score": {"$meta": "searchScore"},
            }
        },
    ]
    cursor = _get_collection().aggregate(pipeline)
    docs = await cursor.to_list(length=top_k)
    for doc in docs:
        doc["id"] = str(doc.pop("_id"))
    return docs


async def get_many_by_ids(chunk_ids: list[str], user_id: str) -> list[DocumentChunk]:
    """Batch fetch by _id, mirroring resource_repository.get_many_by_ids --
    invalid/non-ObjectId ids are silently skipped, not errors. Used by
    retrieval.hybrid_search to turn a fused ranking of chunk ids (from the
    slim vector_search()/text_search() projections, which omit `embedding`
    and other fields not needed for retrieval scoring) back into full
    DocumentChunk objects. `user_id`-scoped as defense-in-depth (Phase 8):
    by construction every id reaching here already came from a
    resource_ids-pre-filtered (hence user-scoped) vector_search/text_search
    call, so this is a second, independent gate rather than the sole one."""
    object_ids = [oid for oid in (_to_object_id(cid) for cid in chunk_ids) if oid is not None]
    if not object_ids:
        return []
    cursor = _get_collection().find({"_id": {"$in": object_ids}, "user_id": user_id})
    docs = await cursor.to_list(length=len(object_ids))
    return [_doc_to_chunk(doc) for doc in docs]


async def reassign_owner(from_user_id: str, to_user_id: str) -> int:
    """One-time migration primitive (Phase 8) -- see
    resource_repository.reassign_owner for the full rationale; identical
    shape, applied to `document_chunks`."""
    result = await _get_collection().update_many(
        {"$or": [{"user_id": from_user_id}, {"user_id": {"$exists": False}}]},
        {"$set": {"user_id": to_user_id}},
    )
    return result.modified_count
