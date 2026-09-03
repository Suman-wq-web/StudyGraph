"""
Collection name constants and planned indexes for MongoDB Atlas.

This module is the single source of truth for collection names -- services
and models import from here rather than hardcoding strings. Index creation
and the Atlas Search / Atlas Vector Search index definitions are documented
here as data for now; actually provisioning them (via `create_index` calls
or the Atlas UI/CLI) is deferred to a later phase. See ARCHITECTURE.md
("MongoDB collections") for field-level schema and rationale.
"""

RESOURCES = "resources"
DOCUMENT_CHUNKS = "document_chunks"
CONCEPTS = "concepts"
EDGES = "edges"
USERS = "users"
RESOURCE_PROGRESS = "resource_progress"

# Standard (non-search) indexes to create per collection, expressed as
# (field, direction) tuples -- planned, not yet applied (provisioning these,
# same as the Atlas Search/Vector Search indexes below, requires explicit
# approval before touching the real cluster -- see docs/DATABASE.md).
# `resources`/`document_chunks` now carry `user_id` (Phase 8) so every
# scoped query (app/db/resource_repository.py, chunk_repository.py) can use
# it as the leading index field, same as `concepts`/`edges` already do.
PLANNED_INDEXES: dict[str, list[tuple[str, int]]] = {
    RESOURCES: [("user_id", 1), ("type", 1), ("created_at", -1)],
    DOCUMENT_CHUNKS: [("resource_id", 1), ("chunk_index", 1)],
    CONCEPTS: [("user_id", 1), ("normalized_name", 1)],
    EDGES: [("user_id", 1), ("source_concept_id", 1), ("target_concept_id", 1)],
    USERS: [("email", 1)],  # intended unique -- see docs/DATABASE.md
    # Compound key is intended unique per (user_id, resource_id) -- one
    # progress row per user per resource, upserted by
    # app/db/progress_repository.py:upsert. Leading with user_id keeps it
    # consistent with every other user-scoped collection above.
    RESOURCE_PROGRESS: [("user_id", 1), ("resource_id", 1)],
}

# Atlas Search (BM25 text) index (Phase 5), used by
# app/db/chunk_repository.py's text_search() -- the keyword half of hybrid
# retrieval, fused with vector_search() in app/services/rag/retrieval.py. See
# docs/DATABASE.md ("Atlas Search (BM25) setup") for the exact index
# definition and setup steps.
ATLAS_SEARCH_INDEX_NAME = "document_chunks_text_search"
ATLAS_SEARCH_INDEX_FIELD = "text"
# Mirrors ATLAS_VECTOR_INDEX_FILTER_FIELDS so hybrid retrieval pre-filters
# both queries by resource_id identically.
ATLAS_SEARCH_INDEX_FILTER_FIELDS = ["resource_id"]

# Atlas Vector Search index (Phase 4), used by app/db/chunk_repository.py's
# vector_search() for semantic retrieval over Gemini embedding vectors --
# NOT OpenAI. Dimensions are deliberately not hard-coded here: they come from
# whatever `settings.gemini_embedding_dimensions` resolves to (None = the
# model's own default, 3072 for gemini-embedding-001). Whoever provisions the
# Atlas index must set its `numDimensions` to match the actual length of the
# vectors being stored (`len(chunk["embedding"])`) -- see docs/DATABASE.md
# ("Atlas Vector Search setup") for the exact index definition and setup
# steps.
ATLAS_VECTOR_INDEX_NAME = "document_chunks_vector_index"
ATLAS_VECTOR_INDEX_FIELD = "embedding"
ATLAS_VECTOR_INDEX_SIMILARITY = "cosine"
# Fields the Atlas Vector Search index must declare as filterable so
# app/db/chunk_repository.py:vector_search()'s resource_ids pre-filter works.
# Phase 8 user isolation deliberately reuses this SAME field rather than
# adding a new `user_id` filterable field: app/services/rag/retrieval.py and
# app/services/search_service.py now always resolve the caller's own
# resource ids first (app/db/resource_repository.py:list_ids_by_filter,
# user_id-scoped) and pass that allowlist through this existing,
# already-provisioned filter -- no Atlas index change required for search
# isolation.
ATLAS_VECTOR_INDEX_FILTER_FIELDS = ["resource_id"]
# gemini-embedding-001's own output size when GEMINI_EMBEDDING_DIMENSIONS is
# unset -- informational only (see the comment above), not authoritative.
GEMINI_EMBEDDING_MODEL_DEFAULT_DIMENSIONS = 3072
