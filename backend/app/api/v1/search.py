"""Semantic similarity search over document_chunks (Phase 4). Read-only
retrieval -- does not generate an answer; that's Phase 5's RAG chat."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user_id
from app.models.embedding import VectorSearchRequest, VectorSearchResponse
from app.services import search_service

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/vector", response_model=VectorSearchResponse)
async def vector_search(
    payload: VectorSearchRequest, current_user_id: str = Depends(get_current_user_id)
) -> VectorSearchResponse:
    """
    Embeds `query` with the configured embedding provider and runs a MongoDB
    Atlas Vector Search against `document_chunks`, restricted to the
    caller's own resources and optionally further pre-filtered by
    `resourceType`/`tags`. Returns raw retrieved chunks plus enough resource
    metadata for future citation tracking -- no generated answer.
    """
    try:
        return await search_service.vector_search(payload, current_user_id)
    except search_service.EmbeddingUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not embed the search query: {exc}",
        ) from exc
    except search_service.VectorSearchUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
