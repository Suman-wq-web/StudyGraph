"""
Persistence for the `resources` collection. This is the only module that turns
`Resource*` Pydantic models into MongoDB documents and back -- the service layer
(app/services/resource_service.py) calls these functions instead of touching
`app/db/mongodb.get_database()` directly, keeping Mongo/ObjectId details out of
the business-logic and HTTP layers.
"""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from app.db import mongodb
from app.db.collections import RESOURCES
from app.models.resource import Resource, ResourceCreate, ResourceStatus, ResourceUpdate


def _get_collection():
    return mongodb.get_database()[RESOURCES]


def _to_object_id(resource_id: str) -> ObjectId | None:
    try:
        return ObjectId(resource_id)
    except (InvalidId, TypeError):
        return None


def _doc_to_resource(doc: dict[str, Any]) -> Resource:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return Resource.model_validate(doc)


async def create(payload: ResourceCreate, user_id: str) -> Resource:
    now = datetime.now(timezone.utc)
    doc = payload.model_dump(mode="json", exclude_none=False)
    doc["user_id"] = user_id
    doc["status"] = ResourceStatus.PENDING.value
    doc["created_at"] = now
    doc["updated_at"] = now

    result = await _get_collection().insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_resource(doc)


async def get_by_id(resource_id: str, user_id: str) -> Resource | None:
    object_id = _to_object_id(resource_id)
    if object_id is None:
        return None
    doc = await _get_collection().find_one({"_id": object_id, "user_id": user_id})
    if doc is None:
        return None
    return _doc_to_resource(doc)


async def list_all(
    *,
    user_id: str,
    type_filter: str | None = None,
    status_filter: str | None = None,
    tag_filter: str | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Resource], int]:
    query: dict[str, Any] = {"user_id": user_id}
    if type_filter:
        query["type"] = type_filter
    if status_filter:
        query["status"] = status_filter
    if tag_filter:
        query["tags"] = tag_filter
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
        ]

    collection = _get_collection()
    total = await collection.count_documents(query)
    cursor = collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [_doc_to_resource(doc) for doc in docs], total


async def update(resource_id: str, payload: ResourceUpdate, user_id: str) -> Resource | None:
    object_id = _to_object_id(resource_id)
    if object_id is None:
        return None

    changes = payload.model_dump(mode="json", exclude_unset=True)
    if not changes:
        return await get_by_id(resource_id, user_id)

    changes["updated_at"] = datetime.now(timezone.utc)

    collection = _get_collection()
    doc = await collection.find_one_and_update(
        {"_id": object_id, "user_id": user_id},
        {"$set": changes},
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        return None
    return _doc_to_resource(doc)


async def get_many_by_ids(resource_ids: list[str], user_id: str) -> list[Resource]:
    """Batch fetch, used to join resource metadata (title/type) onto vector
    search hits and RAG citations -- see app/services/search_service.py,
    app/services/rag/citations.py. `user_id`-scoped as defense-in-depth: by
    construction every caller already resolves `resource_ids` from a
    user_id-scoped query first, so this is a second, independent gate rather
    than the sole one."""
    object_ids = [oid for oid in (_to_object_id(rid) for rid in resource_ids) if oid is not None]
    if not object_ids:
        return []
    cursor = _get_collection().find({"_id": {"$in": object_ids}, "user_id": user_id})
    docs = await cursor.to_list(length=len(object_ids))
    return [_doc_to_resource(doc) for doc in docs]


async def list_ids_by_filter(
    *, user_id: str, type_filter: str | None = None, tag_filter: str | None = None
) -> list[str]:
    """All (unpaginated) resource ids owned by `user_id` matching type/tag,
    for resolving a vector/hybrid search request's filters (including the
    always-applied user scope, Phase 8) into an Atlas $vectorSearch/$search
    pre-filter on the already-indexed `resource_id` field -- see
    app/services/search_service.py, app/services/rag/retrieval.py, and
    app/db/chunk_repository.py:vector_search/text_search."""
    query: dict[str, Any] = {"user_id": user_id}
    if type_filter:
        query["type"] = type_filter
    if tag_filter:
        query["tags"] = tag_filter
    cursor = _get_collection().find(query, {"_id": 1})
    docs = await cursor.to_list(length=None)
    return [str(doc["_id"]) for doc in docs]


async def set_processing_state(
    resource_id: str,
    *,
    status: ResourceStatus,
    error: str | None,
    expected_statuses: tuple[ResourceStatus, ...] | None = None,
) -> Resource | None:
    """
    Sets `status`/`processing_error` directly, bypassing ResourceUpdate --
    these fields are server-managed by the processing pipeline
    (app/services/processing_service.py), not part of the public PATCH
    surface for arbitrary client-supplied error text. Deliberately NOT
    `user_id`-scoped (Phase 8): every caller (processing_service.py,
    embedding_service.py) has already resolved and ownership-checked this
    exact resource_id via a user_id-scoped get_by_id() earlier in the same
    request/background task, so a second filter here would be redundant,
    not an additional guarantee.

    `expected_statuses`, when given, turns this into an atomic
    compare-and-swap: the update only applies if the resource's *current*
    status is one of these, and returns `None` otherwise (same as a missing
    resource_id). This closes the check-then-act race between reading a
    resource's status and flipping it -- see
    app/services/embedding_service.py:start_embedding, which uses it to
    guarantee a resource can't be started embedding twice concurrently.
    `None` (the default) preserves the unconditional `_id`-only update every
    other caller relies on.
    """
    object_id = _to_object_id(resource_id)
    if object_id is None:
        return None

    changes = {
        "status": status.value,
        "processing_error": error,
        "updated_at": datetime.now(timezone.utc),
    }
    query: dict[str, Any] = {"_id": object_id}
    if expected_statuses is not None:
        query["status"] = {"$in": [s.value for s in expected_statuses]}

    doc = await _get_collection().find_one_and_update(
        query, {"$set": changes}, return_document=ReturnDocument.AFTER
    )
    if doc is None:
        return None
    return _doc_to_resource(doc)


async def delete(resource_id: str, user_id: str) -> bool:
    object_id = _to_object_id(resource_id)
    if object_id is None:
        return False
    result = await _get_collection().delete_one({"_id": object_id, "user_id": user_id})
    return result.deleted_count > 0


async def stats(user_id: str) -> dict[str, Any]:
    collection = _get_collection()
    match = {"user_id": user_id}
    total = await collection.count_documents(match)

    by_type: dict[str, int] = {}
    async for doc in collection.aggregate(
        [{"$match": match}, {"$group": {"_id": "$type", "count": {"$sum": 1}}}]
    ):
        by_type[doc["_id"]] = doc["count"]

    by_status: dict[str, int] = {}
    async for doc in collection.aggregate(
        [{"$match": match}, {"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    ):
        by_status[doc["_id"]] = doc["count"]

    return {"total": total, "by_type": by_type, "by_status": by_status}


async def reassign_owner(from_user_id: str, to_user_id: str) -> int:
    """
    One-time migration primitive (Phase 8): reassigns every resource owned
    by `from_user_id` -- or, since `resources` predates the `user_id` field
    entirely, with no `user_id` at all -- to `to_user_id`. A pure `$set`
    update, never a delete/insert; safe to call more than once (a second
    call's filter matches nothing already reassigned). Only ever invoked by
    app/services/migration_service.py via the authenticated
    POST /api/v1/auth/claim-legacy-data, always targeting the caller's own
    id -- see that module for why this can't be pointed at an arbitrary
    user.
    """
    result = await _get_collection().update_many(
        {"$or": [{"user_id": from_user_id}, {"user_id": {"$exists": False}}]},
        {"$set": {"user_id": to_user_id}},
    )
    return result.modified_count
