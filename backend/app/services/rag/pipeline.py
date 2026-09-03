"""
Orchestrates the end-to-end RAG query: hybrid retrieval -> citation
assembly -> prompt construction -> LLM generation (streamed). Two entry
points, for two different callers:

    retrieve_context() + stream_generation()   <- app/api/v1/chat.py (SSE)
    answer_query()                              <- tests / non-HTTP callers

The split exists because citations must be known before generation starts,
but a retrieval failure needs to surface as a normal HTTP 503 -- only
possible *before* the SSE response commits to `text/event-stream`. See
docs/RAG.md ("Generate") and docs/API.md ("/api/v1/chat") for the full
design.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

from app.config import settings
from app.models.chat import (
    ChatCitationsEventData,
    ChatDoneEventData,
    ChatErrorEventData,
    ChatQueryResponse,
    ChatTokenEventData,
    Citation,
)
from app.models.chunk import DocumentChunk
from app.services.rag import citations as citations_service
from app.services.rag import retrieval
from app.services.rag.generation import (
    GenerationChunk,
    GenerationError,
    GenerationProvider,
    GenerationProviderError,
    GenerationRateLimitError,
    GenerationTransientError,
    get_generation_provider,
)

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = (
    "You are StudyGraph's study assistant. Answer the user's question using ONLY "
    "the numbered source excerpts below, drawn from the user's own saved material. "
    "Cite sources inline as [1], [2], etc., matching the excerpt numbers. If the "
    "excerpts don't contain enough information, say so plainly rather than "
    "guessing or using outside knowledge."
)

# Retry budget for acquiring the stream's FIRST chunk only -- same shape as
# embedding_service.py's _embed_with_retry. Once a first chunk has reached
# the client there is no further retry (see stream_generation).
MAX_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 1.0
# Same cap/rationale as embedding_service.MAX_RETRY_DELAY_SECONDS -- this
# retry runs inline in an open HTTP/SSE request the user is waiting on, so
# even a more accurate server-suggested delay still needs an upper bound.
MAX_RETRY_DELAY_SECONDS = 30.0


@dataclass(frozen=True)
class RagContext:
    query: str
    chunks: list[DocumentChunk]
    citations: list[Citation]


@dataclass
class ChatStreamEvent:
    """One SSE frame's worth of data, yielded by `stream_generation`."""

    event: Literal["citations", "token", "done", "error"]
    data: ChatCitationsEventData | ChatTokenEventData | ChatDoneEventData | ChatErrorEventData


async def retrieve_context(
    user_id: str,
    query: str,
    *,
    resource_types: list[str] | None = None,
    tags: list[str] | None = None,
    top_k: int | None = None,
) -> RagContext:
    """
    Phase A of a chat request: hybrid retrieval + citation assembly. Raises
    `retrieval.EmbeddingUnavailableError` / `retrieval.RetrievalUnavailableError`
    -- callers (app/api/v1/chat.py) await this BEFORE opening the SSE stream
    so those exceptions can still become a normal 503.
    """
    filters = retrieval.RetrievalFilters(
        user_id=user_id, resource_types=resource_types, tags=tags
    )
    scored = await retrieval.hybrid_search_with_scores(
        query, filters, top_k if top_k is not None else settings.rag_default_top_k
    )
    scores_by_chunk_id = {chunk.id: score for chunk, score in scored}
    all_chunks = [chunk for chunk, _ in scored]

    built_citations = await citations_service.build_citations(all_chunks, user_id)
    citations = [
        citation.model_copy(update={"score": scores_by_chunk_id.get(citation.chunk_id, 0.0)})
        for citation in built_citations
    ]
    # build_citations may drop a chunk whose resource was deleted between
    # retrieval and this join -- keep `chunks` aligned with `citations` (same
    # order, same membership) so _build_prompt's [n] numbering always matches.
    cited_chunk_ids = {citation.chunk_id for citation in citations}
    chunks = [chunk for chunk in all_chunks if chunk.id in cited_chunk_ids]

    return RagContext(query=query, chunks=chunks, citations=citations)


async def stream_generation(
    context: RagContext, *, provider: GenerationProvider | None = None
) -> AsyncIterator[ChatStreamEvent]:
    """
    Phase B of a chat request. Never raises -- every failure path (missing
    API key, retries exhausted, a mid-stream Gemini failure) yields a
    terminal `error` event and returns instead, mirroring
    embedding_service.run_embedding's "never raise, record failure state
    instead" convention -- except here the "failure state" is an SSE event,
    since chat has no persisted state to update.

    Always yields a `citations` event first (even `citations: []` -- zero
    retrieved chunks is not an error), then zero-or-more `token` events, then
    exactly one `done` or `error` event.
    """
    yield ChatStreamEvent(event="citations", data=ChatCitationsEventData(citations=context.citations))

    try:
        provider = provider or get_generation_provider()
    except GenerationProviderError as exc:
        yield ChatStreamEvent(event="error", data=ChatErrorEventData(message=str(exc)))
        return

    prompt = _build_prompt(context)

    try:
        stream_iter, first_chunk = await _acquire_stream_with_retry(
            provider, system_prompt=RAG_SYSTEM_PROMPT, user_prompt=prompt
        )
    except GenerationProviderError as exc:
        logger.warning("Chat generation unavailable: %s", exc)
        yield ChatStreamEvent(
            event="error",
            data=ChatErrorEventData(
                message="Chat generation is currently unavailable. Please try again shortly."
            ),
        )
        return

    if first_chunk.text:
        yield ChatStreamEvent(event="token", data=ChatTokenEventData(delta=first_chunk.text))
    if first_chunk.finish_reason is not None:
        yield ChatStreamEvent(event="done", data=ChatDoneEventData(finish_reason=first_chunk.finish_reason))
        return

    try:
        async for chunk in stream_iter:
            if chunk.text:
                yield ChatStreamEvent(event="token", data=ChatTokenEventData(delta=chunk.text))
            if chunk.finish_reason is not None:
                yield ChatStreamEvent(
                    event="done", data=ChatDoneEventData(finish_reason=chunk.finish_reason)
                )
                return
    except GenerationError:
        logger.exception("Chat generation failed mid-stream")
        yield ChatStreamEvent(
            event="error",
            data=ChatErrorEventData(message="Chat generation failed partway through. Please try again."),
        )
        return

    # Defensive: the stream ended without a chunk carrying a finish_reason.
    yield ChatStreamEvent(event="done", data=ChatDoneEventData(finish_reason=None))


async def _acquire_stream_with_retry(
    provider: GenerationProvider, *, system_prompt: str, user_prompt: str
) -> tuple[AsyncIterator[GenerationChunk], GenerationChunk]:
    """Retries only up to and including the stream's FIRST chunk
    (rate-limit/transient errors, exponential backoff, MAX_ATTEMPTS budget).
    Once a first chunk is obtained, no further retry happens for this
    request -- restarting generation after partial output was already sent
    to the client would silently duplicate/contradict what they saw."""
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        stream_iter = provider.stream_generate(system_prompt=system_prompt, user_prompt=user_prompt)
        try:
            first_chunk = await stream_iter.__anext__()
            return stream_iter, first_chunk
        except StopAsyncIteration:
            return stream_iter, GenerationChunk(text="", finish_reason="STOP")
        except (GenerationRateLimitError, GenerationTransientError) as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(_backoff_seconds(attempt, exc))
    raise GenerationProviderError(
        f"Generation provider unavailable after {MAX_ATTEMPTS} attempts: {last_error}"
    ) from last_error


def _backoff_seconds(attempt: int, exc: Exception) -> float:
    """`exc` is a GenerationRateLimitError/GenerationTransientError; only the
    former ever carries `retry_delay_seconds` (Gemini's RetryInfo detail is
    429-specific), so a plain `getattr` naturally falls back to exponential
    backoff for transient (5xx) failures too -- mirrors
    embedding_service._backoff_seconds exactly."""
    retry_delay_seconds = getattr(exc, "retry_delay_seconds", None)
    if retry_delay_seconds is not None:
        return min(max(retry_delay_seconds, 0.0), MAX_RETRY_DELAY_SECONDS)
    return BASE_BACKOFF_SECONDS * (2**attempt)


def _build_prompt(context: RagContext) -> str:
    """Numbers excerpts to match `context.citations`' 1-based index, so a
    future frontend can turn an inline "[n]" marker into a link straight to
    `citations[n-1]`."""
    if not context.chunks:
        excerpts = "No relevant saved material was found for this question."
    else:
        excerpts = "\n\n".join(
            f'[{i}] (from "{citation.resource_title}"): {chunk.text}'
            for i, (chunk, citation) in enumerate(zip(context.chunks, context.citations), start=1)
        )
    return f"{excerpts}\n\nQuestion: {context.query}"


async def answer_query(user_id: str, query: str) -> ChatQueryResponse:
    """
    Non-streaming convenience wrapper around retrieve_context() +
    stream_generation(), for tests and any future non-HTTP caller.
    POST /api/v1/chat calls retrieve_context()/stream_generation() directly
    to stream over SSE instead of buffering the whole answer like this does.
    """
    context = await retrieve_context(user_id, query)
    answer_parts: list[str] = []
    async for event in stream_generation(context):
        if event.event == "token":
            answer_parts.append(event.data.delta)
        elif event.event == "error":
            raise RuntimeError(event.data.message)
    return ChatQueryResponse(query=query, answer="".join(answer_parts), citations=context.citations)
