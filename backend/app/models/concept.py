from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Concept(BaseModel):
    """
    Schema for the `concepts` collection: a node in the personal knowledge
    graph, extracted from one or more resources (Phase 6 --
    app/services/graph_extraction_service.py). `centrality_score` is
    computed by the NetworkX graph pipeline (see
    app/services/graph/traversal.py), not stored authoritatively -- it's
    cached here after each `GET /api/v1/graph` rebuild.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    user_id: str
    name: str
    normalized_name: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    source_resource_ids: list[str] = Field(default_factory=list)
    centrality_score: float | None = None
    created_at: datetime
    updated_at: datetime
