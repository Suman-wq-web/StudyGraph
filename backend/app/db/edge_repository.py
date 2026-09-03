"""
Persistence for the `edges` collection (Phase 6). Mirrors
concept_repository.py's pattern -- the only module that turns ConceptEdge
data into Mongo documents and back.
"""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from app.db import mongodb
from app.db.collections import EDGES
from app.models.edge import ConceptEdge, RelationType


def _get_collection():
    return mongodb.get_database()[EDGES]


def _to_object_id(edge_id: str) -> ObjectId | None:
    try:
        return ObjectId(edge_id)
    except (InvalidId, TypeError):
        return None


def _doc_to_edge(doc: dict[str, Any]) -> ConceptEdge:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return ConceptEdge.model_validate(doc)


async def find_by_triple(
    user_id: str,
    source_concept_id: str,
    target_concept_id: str,
    relation_type: RelationType,
) -> ConceptEdge | None:
    doc = await _get_collection().find_one(
        {
            "user_id": user_id,
            "source_concept_id": source_concept_id,
            "target_concept_id": target_concept_id,
            "relation_type": relation_type.value,
        }
    )
    if doc is None:
        return None
    return _doc_to_edge(doc)


async def create(
    *,
    user_id: str,
    source_concept_id: str,
    target_concept_id: str,
    relation_type: RelationType,
    evidence_chunk_id: str,
) -> ConceptEdge:
    doc = {
        "user_id": user_id,
        "source_concept_id": source_concept_id,
        "target_concept_id": target_concept_id,
        "relation_type": relation_type.value,
        "weight": 1.0,
        "evidence_chunk_ids": [evidence_chunk_id],
        "created_at": datetime.now(timezone.utc),
    }
    result = await _get_collection().insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_edge(doc)


async def add_evidence(edge_id: str, chunk_id: str) -> ConceptEdge | None:
    """Idempotent: repeated evidence from the same chunk (e.g. re-running
    extraction for a chunk that was already extracted) is a no-op rather
    than inflating `weight` again -- only evidence from a *new* chunk
    strengthens the edge."""
    object_id = _to_object_id(edge_id)
    if object_id is None:
        return None
    collection = _get_collection()
    existing = await collection.find_one({"_id": object_id})
    if existing is None:
        return None
    if chunk_id in existing.get("evidence_chunk_ids", []):
        return _doc_to_edge(existing)
    doc = await collection.find_one_and_update(
        {"_id": object_id},
        {"$addToSet": {"evidence_chunk_ids": chunk_id}, "$inc": {"weight": 1.0}},
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        return None
    return _doc_to_edge(doc)


async def list_by_user(user_id: str) -> list[ConceptEdge]:
    cursor = _get_collection().find({"user_id": user_id})
    docs = await cursor.to_list(length=None)
    return [_doc_to_edge(doc) for doc in docs]


async def reassign_owner(from_user_id: str, to_user_id: str) -> int:
    """One-time migration primitive (Phase 8) -- see
    resource_repository.reassign_owner / concept_repository.reassign_owner
    for the full rationale; identical shape, applied to `edges`."""
    result = await _get_collection().update_many(
        {"user_id": from_user_id}, {"$set": {"user_id": to_user_id}}
    )
    return result.modified_count
