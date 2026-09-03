"""
One-time, explicit, idempotent migration of pre-auth data (Phase 8): every
`resources`/`document_chunks`/`concepts`/`edges` document written before
real authentication existed is reassigned from the placeholder
single-tenant owner to a real, authenticated user -- never deleted, never
reassigned automatically or to an arbitrary user. Only reachable via
POST /api/v1/auth/claim-legacy-data, which always targets the CALLING
user's own id (see app/api/v1/auth.py) -- there is no way to migrate data
onto anyone else.

`LEGACY_USER_ID` is the exact placeholder string every DEFAULT_USER_ID
constant in the pre-Phase-8 codebase used (app/services/graph_service.py,
graph_extraction_service.py, recommendation_service.py,
app/services/rag/pipeline.py -- all now removed in favor of the real
authenticated user_id, but concepts/edges written before this phase already
carry this exact value). `resources`/`document_chunks` predate the
`user_id` field entirely, so their legacy rows have no such field at all
rather than this placeholder -- each reassign_owner() matches both cases.

Idempotent by construction: once a collection's legacy rows are reassigned,
a second call's $or query matches nothing in it, so repeated calls (by the
same or a different user) are safe no-ops for whatever's already claimed.
"""

from dataclasses import dataclass

from app.db import chunk_repository, concept_repository, edge_repository, resource_repository

LEGACY_USER_ID = "single-tenant-user"


@dataclass(frozen=True)
class MigrationCounts:
    resources_migrated: int
    document_chunks_migrated: int
    concepts_migrated: int
    edges_migrated: int


async def migrate_legacy_data(new_user_id: str) -> MigrationCounts:
    resources = await resource_repository.reassign_owner(LEGACY_USER_ID, new_user_id)
    chunks = await chunk_repository.reassign_owner(LEGACY_USER_ID, new_user_id)
    concepts = await concept_repository.reassign_owner(LEGACY_USER_ID, new_user_id)
    edges = await edge_repository.reassign_owner(LEGACY_USER_ID, new_user_id)
    return MigrationCounts(
        resources_migrated=resources,
        document_chunks_migrated=chunks,
        concepts_migrated=concepts,
        edges_migrated=edges,
    )
