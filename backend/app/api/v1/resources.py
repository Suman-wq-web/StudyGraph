"""Routes for saving/listing/updating/deleting resources (articles, videos, URLs, notes),
and for triggering/observing their document-processing pipeline (Phase 3)."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from app.api.deps import get_current_user_id
from app.models.embedding import EmbeddingStatusResponse
from app.models.graph import ExtractionStatusResponse, ExtractionTriggerResponse
from app.models.processing import ProcessingStatusResponse
from app.models.progress import InProgressResourcesResponse, ProgressUpdate, ResourceProgress
from app.models.resource import (
    Resource,
    ResourceCreate,
    ResourceListResponse,
    ResourceStats,
    ResourceStatus,
    ResourceType,
    ResourceUpdate,
)
from app.services import (
    embedding_service,
    graph_extraction_service,
    processing_service,
    progress_service,
    resource_service,
)

router = APIRouter(prefix="/resources", tags=["resources"])


@router.post("", response_model=Resource, status_code=status.HTTP_201_CREATED)
async def create_resource(
    payload: ResourceCreate, current_user_id: str = Depends(get_current_user_id)
) -> Resource:
    return await resource_service.create_resource(payload, current_user_id)


@router.get("", response_model=ResourceListResponse)
async def list_resources(
    type: ResourceType | None = None,
    status_: ResourceStatus | None = Query(default=None, alias="status"),
    tag: str | None = None,
    search: str | None = Query(default=None, max_length=200),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user_id: str = Depends(get_current_user_id),
) -> ResourceListResponse:
    return await resource_service.list_resources(
        user_id=current_user_id,
        type_filter=type.value if type else None,
        status_filter=status_.value if status_ else None,
        tag=tag,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.get("/stats", response_model=ResourceStats)
async def get_resource_stats(current_user_id: str = Depends(get_current_user_id)) -> ResourceStats:
    return await resource_service.get_stats(current_user_id)


@router.get("/progress/in-progress", response_model=InProgressResourcesResponse)
async def list_in_progress_resources(
    limit: int = Query(default=10, ge=1, le=50),
    current_user_id: str = Depends(get_current_user_id),
) -> InProgressResourcesResponse:
    """
    The Dashboard's "Continue learning" data source: this user's resources
    currently `in_progress` (never `not_started` or `completed`), newest
    activity first. Declared before GET /{resource_id} -- same reason
    /stats is -- so "progress" isn't swallowed as a resource_id.
    """
    return await progress_service.list_in_progress(current_user_id, limit=limit)


@router.get("/{resource_id}", response_model=Resource)
async def get_resource(resource_id: str, current_user_id: str = Depends(get_current_user_id)) -> Resource:
    resource = await resource_service.get_resource(resource_id, current_user_id)
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return resource


@router.patch("/{resource_id}", response_model=Resource)
async def update_resource(
    resource_id: str, payload: ResourceUpdate, current_user_id: str = Depends(get_current_user_id)
) -> Resource:
    resource = await resource_service.update_resource(resource_id, payload, current_user_id)
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return resource


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(resource_id: str, current_user_id: str = Depends(get_current_user_id)) -> None:
    deleted = await resource_service.delete_resource(resource_id, current_user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")


@router.post(
    "/{resource_id}/process", response_model=Resource, status_code=status.HTTP_202_ACCEPTED
)
async def process_resource(
    resource_id: str,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user_id),
) -> Resource:
    """
    Starts (or restarts) the document-processing pipeline for a resource:
    extract content -> normalize -> chunk with tiktoken -> write
    `document_chunks`. Returns immediately with status=PROCESSING; the
    pipeline itself runs as a background task. Poll
    GET /{resource_id}/processing-status for the outcome. Re-processing is
    idempotent -- it replaces the resource's existing chunks rather than
    accumulating duplicates.
    """
    try:
        resource = await processing_service.start_processing(resource_id, current_user_id)
    except processing_service.ResourceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found"
        ) from exc
    except processing_service.AlreadyProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Resource is already being processed"
        ) from exc

    background_tasks.add_task(processing_service.run_processing, resource_id, current_user_id)
    return resource


@router.get("/{resource_id}/processing-status", response_model=ProcessingStatusResponse)
async def get_processing_status(
    resource_id: str, current_user_id: str = Depends(get_current_user_id)
) -> ProcessingStatusResponse:
    result = await processing_service.get_processing_status(resource_id, current_user_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    resource, chunk_count = result
    return ProcessingStatusResponse(
        resource_id=resource.id,
        status=resource.status,
        chunk_count=chunk_count,
        processing_error=resource.processing_error,
        updated_at=resource.updated_at,
    )


@router.post(
    "/{resource_id}/extract",
    response_model=ExtractionTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def extract_resource(
    resource_id: str,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user_id),
) -> ExtractionTriggerResponse:
    """
    Starts (or restarts) concept/relationship extraction for a chunked
    resource's chunks with the configured generation provider (Gemini, via
    the same abstraction Phase 5 chat uses -- see
    app/services/ingestion/extraction.py) and upserts the results into
    `concepts`/`edges`. Requires the resource to already be chunked (i.e.
    `POST /{resource_id}/process` must have succeeded first). Returns
    immediately with how many chunks are currently unextracted; the pipeline
    runs as a background task. Poll GET /{resource_id}/extraction-status for
    progress. Idempotent -- chunks already extracted are skipped, and
    resolved concepts/edges are upserted rather than duplicated.
    """
    try:
        pending = await graph_extraction_service.start_extraction(resource_id, current_user_id)
    except graph_extraction_service.ResourceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found"
        ) from exc
    except graph_extraction_service.NoChunksToExtractError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resource must be processed (chunked) before concepts can be extracted",
        ) from exc

    background_tasks.add_task(
        graph_extraction_service.run_extraction, resource_id, current_user_id
    )
    return ExtractionTriggerResponse(resource_id=resource_id, chunks_pending=pending)


@router.get("/{resource_id}/extraction-status", response_model=ExtractionStatusResponse)
async def get_extraction_status(
    resource_id: str, current_user_id: str = Depends(get_current_user_id)
) -> ExtractionStatusResponse:
    result = await graph_extraction_service.get_extraction_status(resource_id, current_user_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    resource, extracted_count, total_count = result
    return ExtractionStatusResponse(
        resource_id=resource.id,
        extracted_chunk_count=extracted_count,
        total_chunk_count=total_count,
        updated_at=resource.updated_at,
    )


@router.post("/{resource_id}/embed", response_model=Resource, status_code=status.HTTP_202_ACCEPTED)
async def embed_resource(
    resource_id: str,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user_id),
) -> Resource:
    """
    Starts (or restarts) embedding a chunked resource's chunks with the
    configured embedding provider (Gemini by default -- see
    app/services/rag/embeddings.py) and storing the vectors on
    `document_chunks`. Requires the resource to already be chunked
    (`status=ready`, `EMBEDDED`, or `FAILED` with existing chunks -- i.e.
    POST /{resource_id}/process must have succeeded first). Returns
    immediately with status=EMBEDDING; the pipeline runs as a background
    task. Poll GET /{resource_id}/embedding-status for the outcome.
    Idempotent -- chunks that already have an embedding are not re-embedded.
    """
    try:
        resource = await embedding_service.start_embedding(resource_id, current_user_id)
    except embedding_service.ResourceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found"
        ) from exc
    except embedding_service.AlreadyEmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Resource is already being embedded"
        ) from exc
    except embedding_service.NotReadyForEmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resource must be processed (chunked) before it can be embedded",
        ) from exc

    background_tasks.add_task(embedding_service.run_embedding, resource_id)
    return resource


@router.get("/{resource_id}/embedding-status", response_model=EmbeddingStatusResponse)
async def get_embedding_status(
    resource_id: str, current_user_id: str = Depends(get_current_user_id)
) -> EmbeddingStatusResponse:
    result = await embedding_service.get_embedding_status(resource_id, current_user_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    resource, embedded_count, total_count = result
    return EmbeddingStatusResponse(
        resource_id=resource.id,
        status=resource.status,
        embedded_chunk_count=embedded_count,
        total_chunk_count=total_count,
        processing_error=resource.processing_error,
        updated_at=resource.updated_at,
    )


@router.get("/{resource_id}/progress", response_model=ResourceProgress)
async def get_resource_progress(
    resource_id: str, current_user_id: str = Depends(get_current_user_id)
) -> ResourceProgress:
    """Reading/watch progress for this resource. Returns a `not_started`
    default (not 404) for a resource that exists but has no activity yet --
    see app/services/progress_service.py:get_progress."""
    progress = await progress_service.get_progress(resource_id, current_user_id)
    if progress is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return progress


@router.patch("/{resource_id}/progress", response_model=ResourceProgress)
async def update_resource_progress(
    resource_id: str, payload: ProgressUpdate, current_user_id: str = Depends(get_current_user_id)
) -> ResourceProgress:
    """
    Saves reading/watch progress. Called periodically by the video player
    (positionSeconds/durationSeconds) or the reading-progress tracker
    (progressPercent) -- see app/services/progress_service.py for how
    status is derived when the caller doesn't send one explicitly, and how
    reaching COMPLETION_THRESHOLD_PERCENT auto-completes.
    """
    progress = await progress_service.update_progress(resource_id, current_user_id, payload)
    if progress is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return progress


@router.post("/{resource_id}/progress/complete", response_model=ResourceProgress)
async def complete_resource_progress(
    resource_id: str, current_user_id: str = Depends(get_current_user_id)
) -> ResourceProgress:
    """Explicit "Mark as complete/read" action -- sets status=completed,
    progressPercent=100, regardless of prior progress."""
    progress = await progress_service.mark_completed(resource_id, current_user_id)
    if progress is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return progress
