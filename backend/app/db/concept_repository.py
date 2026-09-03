"""
Persistence for the `concepts` collection (Phase 6). Mirrors
resource_repository.py/chunk_repository.py's pattern: the only module that
turns Concept data into Mongo documents and back --
app/services/graph_extraction_service.py calls into this rather than
touching app/db/mongodb.get_database() directly.
"""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from app.db import mongodb
from app.db.collections import CONCEPTS
from app.models.concept import Concept


def _get_collection():
    return mongodb.get_database()[CONCEPTS]


def _to_object_id(concept_id: str) -> ObjectId | None:
    try:
        return ObjectId(concept_id)
    except (InvalidId, TypeError):
        return None


def _doc_to_concept(doc: dict[str, Any]) -> Concept:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return Concept.model_validate(doc)


async def find_by_normalized_name(user_id: str, normalized_name: str) -> Concept | None:
    """The resolution/dedupe lookup: exact match on the caller's already-
    normalized name, scoped to one user. Embedding-similarity dedupe is a
    later refinement (see docs/KNOWLEDGE_GRAPH.md) -- not implemented here."""
    doc = await _get_collection().find_one(
        {"user_id": user_id, "normalized_name": normalized_name}
    )
    if doc is None:
        return None
    return _doc_to_concept(doc)


async def create(
    *,
    user_id: str,
    name: str,
    normalized_name: str,
    description: str | None,
    source_resource_id: str,
) -> Concept:
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "name": name,
        "normalized_name": normalized_name,
        "description": description,
        "aliases": [],
        "source_resource_ids": [source_resource_id],
        "centrality_score": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await _get_collection().insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_concept(doc)


async def add_source_resource(concept_id: str, resource_id: str) -> Concept | None:
    """Idempotent: the same concept mentioned again in the same (or another)
    resource adds that resource id to `source_resource_ids` rather than
    creating a duplicate concept -- `$addToSet` is a no-op if it's already
    present, so re-running extraction for an already-extracted chunk (which
    shouldn't happen, but isn't guarded against at the trigger level -- see
    graph_extraction_service.start_extraction) can't accumulate duplicates."""
    object_id = _to_object_id(concept_id)
    if object_id is None:
        return None
    doc = await _get_collection().find_one_and_update(
        {"_id": object_id},
        {
            "$addToSet": {"source_resource_ids": resource_id},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        return None
    return _doc_to_concept(doc)


async def list_by_user(user_id: str) -> list[Concept]:
    cursor = _get_collection().find({"user_id": user_id})
    docs = await cursor.to_list(length=None)
    return [_doc_to_concept(doc) for doc in docs]


async def reassign_owner(from_user_id: str, to_user_id: str) -> int:
    """One-time migration primitive (Phase 8) -- see
    resource_repository.reassign_owner for the full rationale. `concepts`
    already always carries a `user_id` (the old DEFAULT_USER_ID placeholder,
    pre-Phase-8), so this only ever matches on the exact value, never the
    field-missing case resources/document_chunks additionally need."""
    result = await _get_collection().update_many(
        {"user_id": from_user_id}, {"$set": {"user_id": to_user_id}}
    )
    return result.modified_count


async def set_centrality_scores(scores: dict[str, float]) -> None:
    """Bulk write-back cache after a graph rebuild -- see
    app/services/graph/traversal.py:compute_centrality and
    app/services/graph_service.py. Best-effort: a concept id that no longer
    exists is silently skipped rather than raising."""
    collection = _get_collection()
    for concept_id, score in scores.items():
        object_id = _to_object_id(concept_id)
        if object_id is None:
            continue
        await collection.update_one({"_id": object_id}, {"$set": {"centrality_score": score}})
