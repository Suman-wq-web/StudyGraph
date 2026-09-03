from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.models.resource import ResourceStatus, ResourceType


class EmbeddingStatusResponse(BaseModel):
    """Response body for GET /resources/{id}/embedding-status."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    resource_id: str
    status: ResourceStatus
    embedded_chunk_count: int
    total_chunk_count: int
    processing_error: str | None = None
    updated_at: datetime


class VectorSearchRequest(BaseModel):
    """Request body for POST /search/vector."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    resource_type: ResourceType | None = None
    tags: list[str] | None = Field(default=None, max_length=20)


class VectorSearchResultItem(BaseModel):
    """
    One retrieved chunk plus enough resource metadata for future citation
    tracking (Phase 5 links an answer back to this). No generated answer --
    this endpoint only returns raw retrieval results.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    chunk_id: str
    resource_id: str
    resource_title: str
    resource_type: ResourceType
    chunk_index: int
    text: str
    score: float


class VectorSearchResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    query: str
    results: list[VectorSearchResultItem]
    count: int
