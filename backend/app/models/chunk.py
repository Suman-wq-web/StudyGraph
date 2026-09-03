from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ChunkMetadata(BaseModel):
    """
    Reserved for future citation context (which heading/page/timestamp a
    chunk came from). Not populated by Phase 3 -- extraction doesn't detect
    structure yet -- but kept on the schema now so a later phase can start
    filling it in without a migration.
    """

    heading: str | None = None
    page_number: int | None = None
    start_time_seconds: int | None = None
    end_time_seconds: int | None = None


class DocumentChunk(BaseModel):
    """
    Schema for the `document_chunks` collection: the unit of retrieval for
    future RAG. Produced by app/services/ingestion/chunking.py (tiktoken,
    512-token window / 64-token overlap by default -- see
    app/config.py:chunk_size_tokens/chunk_overlap_tokens).

    `embedding` stays null until Phase 4 populates it with a Gemini
    embedding vector; Phase 3 never writes a fake one. `user_id` (Phase 8,
    denormalized from the parent resource at write time -- see
    app/db/chunk_repository.py:replace_chunks_for_resource) is required,
    no default, same rationale as Resource.user_id (app/models/resource.py).
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    user_id: str
    resource_id: str
    chunk_index: int
    text: str
    token_count: int
    start_token: int
    end_token: int
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata)
    embedding: list[float] | None = None
    # Phase 6: set once a Gemini extraction pass has produced (or attempted
    # and given up on) concepts/relationships for this chunk -- see
    # app/services/graph_extraction_service.py. Mirrors `embedding`'s
    # null-until-done idempotency signal, but as a bool: unlike embedding,
    # a chunk with no extractable concepts is still "done", not absent.
    concepts_extracted: bool = False
    created_at: datetime
    updated_at: datetime
