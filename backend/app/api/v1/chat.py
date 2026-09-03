"""RAG query endpoint (question -> streamed answer + citations, Phase 5)."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user_id
from app.models.chat import ChatQueryRequest
from app.services.rag import generation, pipeline, retrieval

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat_query(
    payload: ChatQueryRequest, current_user_id: str = Depends(get_current_user_id)
) -> StreamingResponse:
    """
    Retrieves relevant chunks via hybrid search, then streams a Gemini-
    generated, citation-grounded answer as Server-Sent Events. Retrieval
    (Phase A) is awaited BEFORE the SSE response is opened, so a
    misconfigured provider or an unavailable retriever still surfaces as a
    normal 503 -- once streaming starts, any failure can only appear as a
    terminal SSE `error` event (see app/services/rag/pipeline.py).
    """
    try:
        provider = generation.get_generation_provider()
    except generation.GenerationProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Chat generation is unavailable: {exc}",
        ) from exc

    try:
        context = await pipeline.retrieve_context(
            current_user_id,
            payload.query,
            resource_types=[payload.resource_type.value] if payload.resource_type else None,
            tags=payload.tags,
            top_k=payload.top_k,
        )
    except retrieval.EmbeddingUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not embed the chat query: {exc}",
        ) from exc
    except retrieval.RetrievalUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    async def event_stream():
        async for item in pipeline.stream_generation(context, provider=provider):
            yield f"event: {item.event}\ndata: {item.data.model_dump_json(by_alias=True)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
