from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.models.resource import ResourceType


class Citation(BaseModel):
    """
    A single citation linking part of a RAG answer back to its source
    chunk/resource. Field set mirrors app/models/embedding.py's
    VectorSearchResultItem (resource_id/resource_title/resource_type/
    chunk_index) plus `snippet` (a truncated preview -- see
    app/services/rag/citations.py:_snippet) and `score` (the chunk's fused
    reciprocal-rank-fusion score from app/services/rag/retrieval.py --
    unbounded, not a [0,1] similarity; higher is more relevant).
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    resource_id: str
    resource_title: str
    resource_type: ResourceType
    chunk_id: str
    chunk_index: int
    snippet: str
    score: float = 0.0


class ChatQueryRequest(BaseModel):
    """Request body for POST /api/v1/chat. Mirrors VectorSearchRequest's
    filter fields (app/models/embedding.py); `top_k` defaults lower (8 vs 5)
    and caps lower (20 vs 50) since it bounds how many chunks are stuffed
    into the LLM prompt, not just a result list."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=20)
    resource_type: ResourceType | None = None
    tags: list[str] | None = Field(default=None, max_length=20)


class ChatQueryResponse(BaseModel):
    """
    Non-streaming response shape, produced by
    app/services/rag/pipeline.py:answer_query() -- a convenience wrapper
    around the real streaming pipeline, used by tests and any future
    non-HTTP caller. POST /api/v1/chat itself streams via SSE instead; see
    ChatStreamEvent and the *EventData models below for that shape.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    query: str
    answer: str
    citations: list[Citation]


class ChatCitationsEventData(BaseModel):
    """Payload of the SSE `citations` event -- always sent first, before any
    `token` event, even when `citations` is empty (zero retrieved chunks is
    not an error)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    citations: list[Citation]


class ChatTokenEventData(BaseModel):
    """Payload of an SSE `token` event -- one streamed answer delta, in
    generation order."""

    delta: str


class ChatDoneEventData(BaseModel):
    """Payload of the terminal SSE `done` event, sent exactly once on a
    successful stream."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    finish_reason: str | None = None


class ChatErrorEventData(BaseModel):
    """Payload of a terminal SSE `error` event -- generation failed after
    the HTTP response had already committed to `text/event-stream`, so the
    failure can't become a normal (e.g. 503) status code; this is the SSE
    equivalent."""

    message: str
