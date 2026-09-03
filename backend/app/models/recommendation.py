from enum import Enum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class RecommendationReasonType(str, Enum):
    """Which v1 heuristic (app/services/graph/recommendations.py) produced
    this recommendation -- see docs/KNOWLEDGE_GRAPH.md ("Phase 7")."""

    GAP = "gap"
    NEXT_STEP = "next_step"


class Recommendation(BaseModel):
    """
    One "what to learn next" suggestion, deterministically derived from the
    user's existing `concepts`/`edges` graph (centrality, source coverage,
    `prerequisite_of` structure) -- no LLM call, no mastery/completion data
    (the schema has none). `reason` is a templated, numbers-backed sentence
    built in recommendation_service.py, not model-generated text.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    concept_id: str
    concept_name: str
    reason_type: RecommendationReasonType
    reason: str
    score: float
    related_concept_ids: list[str] = Field(default_factory=list)
    source_resource_ids: list[str] = Field(default_factory=list)


class RecommendationResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    items: list[Recommendation]
