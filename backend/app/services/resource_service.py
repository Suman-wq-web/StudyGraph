"""
Business logic for saving/listing/updating/deleting resources. Routes in
app/api/v1/resources.py call into this module rather than touching app/db
directly, so persistence details stay isolated from the HTTP layer.
"""

from app.db import chunk_repository, progress_repository, resource_repository
from app.models.resource import (
    Resource,
    ResourceCreate,
    ResourceListResponse,
    ResourceStats,
    ResourceUpdate,
)


async def create_resource(payload: ResourceCreate, user_id: str) -> Resource:
    return await resource_repository.create(payload, user_id)


async def get_resource(resource_id: str, user_id: str) -> Resource | None:
    return await resource_repository.get_by_id(resource_id, user_id)


async def list_resources(
    *,
    user_id: str,
    type_filter: str | None = None,
    status_filter: str | None = None,
    tag: str | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> ResourceListResponse:
    items, total = await resource_repository.list_all(
        user_id=user_id,
        type_filter=type_filter,
        status_filter=status_filter,
        tag_filter=tag,
        search=search,
        skip=skip,
        limit=limit,
    )
    return ResourceListResponse(items=items, total=total, skip=skip, limit=limit)


async def update_resource(resource_id: str, payload: ResourceUpdate, user_id: str) -> Resource | None:
    return await resource_repository.update(resource_id, payload, user_id)


async def delete_resource(resource_id: str, user_id: str) -> bool:
    deleted = await resource_repository.delete(resource_id, user_id)
    if deleted:
        await chunk_repository.delete_by_resource(resource_id)
        await progress_repository.delete_by_resource(resource_id)
    return deleted


async def get_stats(user_id: str) -> ResourceStats:
    data = await resource_repository.stats(user_id)
    return ResourceStats(**data)
