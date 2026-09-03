"""
Persistence for the `resource_progress` collection. Mirrors
resource_repository.py's pattern: the only module that turns progress data
into Mongo documents and back -- app/services/progress_service.py calls
into this rather than touching app/db/mongodb.get_database() directly.

One document per (user_id, resource_id) pair, upserted rather than
inserted -- there is no separate "create" call, since the first progress
update for a resource and every subsequent one go through the same
upsert().
"""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from app.db import mongodb
from app.db.collections import RESOURCE_PROGRESS
from app.models.progress import ProgressStatus, ResourceProgress


def _get_collection():
    return mongodb.get_database()[RESOURCE_PROGRESS]


def _to_object_id(progress_id: str) -> ObjectId | None:
    try:
        return ObjectId(progress_id)
    except (InvalidId, TypeError):
        return None


def _doc_to_progress(doc: dict[str, Any]) -> ResourceProgress:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return ResourceProgress.model_validate(doc)


async def get(*, user_id: str, resource_id: str) -> ResourceProgress | None:
    doc = await _get_collection().find_one({"user_id": user_id, "resource_id": resource_id})
    if doc is None:
        return None
    return _doc_to_progress(doc)


async def upsert(*, user_id: str, resource_id: str, changes: dict[str, Any]) -> ResourceProgress:
    """Applies `changes` (already-resolved status/progress_percent/position_seconds/
    duration_seconds, computed by progress_service) to this user's progress row for
    this resource, creating it on first write. `user_id`/`resource_id` themselves
    come from the query filter on insert -- Mongo's upsert fills them in
    automatically, so they're deliberately not repeated in `changes`."""
    now = datetime.now(timezone.utc)
    set_fields = dict(changes)
    set_fields["updated_at"] = now

    doc = await _get_collection().find_one_and_update(
        {"user_id": user_id, "resource_id": resource_id},
        {
            "$set": set_fields,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return _doc_to_progress(doc)


async def list_in_progress(*, user_id: str, limit: int = 10) -> list[ResourceProgress]:
    cursor = (
        _get_collection()
        .find({"user_id": user_id, "status": ProgressStatus.IN_PROGRESS.value})
        .sort("updated_at", -1)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    return [_doc_to_progress(doc) for doc in docs]


async def delete_by_resource(resource_id: str) -> int:
    """Cascade delete, called from resource_service.delete_resource --
    deliberately NOT user_id-scoped, same rationale as
    resource_repository.set_processing_state: the caller has already
    ownership-checked this resource_id via a user_id-scoped lookup earlier
    in the same request."""
    result = await _get_collection().delete_many({"resource_id": resource_id})
    return result.deleted_count
