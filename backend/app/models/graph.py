from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ExtractionTriggerResponse(BaseModel):
    """Response body for POST /resources/{id}/extract. Unlike /process and
    /embed, there is no Resource.status change to report (see
    app/services/graph_extraction_service.py for why) -- this instead
    reports how many chunks were unextracted at trigger time, so a caller
    has an immediate sense of scope before polling extraction-status."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    resource_id: str
    chunks_pending: int


class ExtractionStatusResponse(BaseModel):
    """Response body for GET /resources/{id}/extraction-status."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    resource_id: str
    extracted_chunk_count: int
    total_chunk_count: int
    updated_at: datetime


class GraphNode(BaseModel):
    """One `concepts` document serialized for GET /api/v1/graph --
    react-force-graph consumes `id`/`name` directly; `centralityScore` is
    freshly computed by app/services/graph/traversal.py on every request."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    name: str
    description: str | None = None
    source_resource_ids: list[str] = Field(default_factory=list)
    centrality_score: float | None = None


class GraphEdgeResponse(BaseModel):
    """One `edges` document serialized for GET /api/v1/graph.
    `source`/`target` are concept ids, matching react-force-graph's expected
    link shape."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    source: str
    target: str
    relation_type: str
    weight: float


class GraphResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    nodes: list[GraphNode]
    edges: list[GraphEdgeResponse]
