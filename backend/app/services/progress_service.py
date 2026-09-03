"""
Business logic for reading/watching progress on a resource. Routes in
app/api/v1/resources.py call into this module rather than touching app/db
directly -- mirrors resource_service.py's shape.

Every function here first re-resolves the resource via a user_id-scoped
resource_repository.get_by_id -- the caller owning the resource_id is what
makes every progress read/write safe to trust, and it doubles as the
"resource exists and isn't someone else's / hasn't been deleted" check
(requirement: progress must be user-isolated and handle deleted resources
gracefully).
"""

from app.db import progress_repository, resource_repository
from app.models.progress import (
    COMPLETION_THRESHOLD_PERCENT,
    InProgressResource,
    InProgressResourcesResponse,
    ProgressStatus,
    ProgressUpdate,
    ResourceProgress,
)


def _derive_status_and_percent(
    payload_fields: dict, existing: ResourceProgress | None
) -> tuple[ProgressStatus, float | None]:
    """
    Works out the final status/progress_percent for an update given only the
    fields the caller actually sent (`payload_fields`, from
    `ProgressUpdate.model_dump(exclude_unset=True)`):

    - An explicit `status` always wins outright (e.g. a "mark as complete"
      action, or resetting to not_started).
    - Otherwise, a `progressPercent` is used directly if sent; failing that,
      it's computed from `positionSeconds`/`durationSeconds` (the video
      player's periodic saves send position/duration, not a percent).
    - Reaching COMPLETION_THRESHOLD_PERCENT auto-promotes to completed
      (capped at 100), matching a video/article naturally finishing without
      the caller having to say so explicitly.
    - A position/duration update with no computable percent (duration not
      yet known) still counts as "in progress" -- the user has clearly
      started.
    """
    status = payload_fields.get("status")
    progress_percent = payload_fields.get("progress_percent")
    position_seconds = payload_fields.get("position_seconds")
    duration_seconds = payload_fields.get("duration_seconds")

    if duration_seconds is None:
        duration_seconds = existing.duration_seconds if existing else None

    if progress_percent is None and position_seconds is not None and duration_seconds:
        progress_percent = min(100.0, round((position_seconds / duration_seconds) * 100, 2))

    if status is not None:
        status = ProgressStatus(status)
        if status == ProgressStatus.COMPLETED:
            progress_percent = 100.0
        elif status == ProgressStatus.NOT_STARTED:
            progress_percent = 0.0
        return status, progress_percent

    if progress_percent is not None:
        if progress_percent >= COMPLETION_THRESHOLD_PERCENT:
            return ProgressStatus.COMPLETED, 100.0
        if progress_percent > 0:
            return ProgressStatus.IN_PROGRESS, progress_percent
        return ProgressStatus.NOT_STARTED, progress_percent

    # Position/duration given but no percent computable yet (duration unknown) --
    # still a clear "the user opened/started this".
    return ProgressStatus.IN_PROGRESS, progress_percent


async def get_progress(resource_id: str, user_id: str) -> ResourceProgress | None:
    """Returns None only when the resource itself doesn't exist/isn't the
    caller's -- for an owned resource with no activity yet, returns a
    synthesized `not_started` default rather than None, since that's a
    normal state, not a 404."""
    resource = await resource_repository.get_by_id(resource_id, user_id)
    if resource is None:
        return None
    progress = await progress_repository.get(user_id=user_id, resource_id=resource_id)
    if progress is not None:
        return progress
    return ResourceProgress(user_id=user_id, resource_id=resource_id)


async def update_progress(
    resource_id: str, user_id: str, payload: ProgressUpdate
) -> ResourceProgress | None:
    resource = await resource_repository.get_by_id(resource_id, user_id)
    if resource is None:
        return None

    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return await get_progress(resource_id, user_id)

    existing = await progress_repository.get(user_id=user_id, resource_id=resource_id)
    status, progress_percent = _derive_status_and_percent(fields, existing)

    changes: dict = {"status": status.value}
    if progress_percent is not None:
        changes["progress_percent"] = progress_percent
    if "position_seconds" in fields:
        changes["position_seconds"] = fields["position_seconds"]
    if "duration_seconds" in fields:
        changes["duration_seconds"] = fields["duration_seconds"]

    return await progress_repository.upsert(user_id=user_id, resource_id=resource_id, changes=changes)


async def mark_completed(resource_id: str, user_id: str) -> ResourceProgress | None:
    resource = await resource_repository.get_by_id(resource_id, user_id)
    if resource is None:
        return None
    return await progress_repository.upsert(
        user_id=user_id,
        resource_id=resource_id,
        changes={"status": ProgressStatus.COMPLETED.value, "progress_percent": 100.0},
    )


async def list_in_progress(user_id: str, limit: int = 10) -> InProgressResourcesResponse:
    progress_docs = await progress_repository.list_in_progress(user_id=user_id, limit=limit)
    if not progress_docs:
        return InProgressResourcesResponse(items=[])

    resource_ids = [doc.resource_id for doc in progress_docs]
    resources = await resource_repository.get_many_by_ids(resource_ids, user_id)
    resources_by_id = {resource.id: resource for resource in resources}

    items: list[InProgressResource] = []
    for doc in progress_docs:
        resource = resources_by_id.get(doc.resource_id)
        if resource is None:
            # Orphaned progress row (resource deleted without the normal
            # cascade, e.g. pre-existing data) -- skip rather than error.
            continue
        items.append(
            InProgressResource(
                resource_id=resource.id,
                title=resource.title,
                type=resource.type,
                status=doc.status,
                progress_percent=doc.progress_percent,
                position_seconds=doc.position_seconds,
                duration_seconds=doc.duration_seconds,
                updated_at=doc.updated_at,
            )
        )
    return InProgressResourcesResponse(items=items)
