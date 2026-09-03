from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class RelationType(str, Enum):
    PREREQUISITE_OF = "prerequisite_of"
    RELATED_TO = "related_to"
    PART_OF = "part_of"


class ConceptEdge(BaseModel):
    """
    Schema for the `edges` collection: a directed relationship between two
    `concepts`, with evidence back to the chunks it was extracted from.
    Written by app/services/graph_extraction_service.py (Phase 6), consumed
    by app/services/graph/builder.py to construct the NetworkX graph.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    user_id: str
    source_concept_id: str
    target_concept_id: str
    relation_type: RelationType
    weight: float = 1.0
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    created_at: datetime
