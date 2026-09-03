"""
Opt-in END-TO-END integration test: real Gemini embeddings + a real MongoDB
Atlas cluster with `document_chunks_vector_index` already provisioned (see
docs/DATABASE.md, "Atlas Vector Search setup"). Skipped by default -- this is
the only place in the suite that exercises real MongoDB Atlas Vector Search;
everywhere else mocks `chunk_repository.vector_search` (see test_search.py),
since a local, non-Atlas MongoDB cannot run `$vectorSearch` at all.

Enable with:
    RUN_ATLAS_VECTOR_SEARCH_TESTS=1 GEMINI_API_KEY=<real key> \\
    MONGODB_URI=<Atlas SRV string> pytest tests/test_atlas_integration.py

Creates and deletes its own resource/chunks -- leaves no data behind, even on
failure (best-effort cleanup in a `finally`).
"""

import asyncio
import os

import pytest

from app.db import chunk_repository, mongodb, resource_repository
from app.models.embedding import VectorSearchRequest
from app.models.resource import ResourceCreate, ResourceType
from app.services import embedding_service, processing_service, search_service

_RUN = os.environ.get("RUN_ATLAS_VECTOR_SEARCH_TESTS") == "1"
_API_KEY = os.environ.get("GEMINI_API_KEY", "")

pytestmark = pytest.mark.skipif(
    not _RUN or not _API_KEY,
    reason=(
        "Set RUN_ATLAS_VECTOR_SEARCH_TESTS=1, a real GEMINI_API_KEY, and MONGODB_URI pointing "
        "at an Atlas cluster with document_chunks_vector_index already provisioned to run this."
    ),
)


def test_real_end_to_end_chunk_embed_and_vector_search():
    async def scenario():
        mongodb.connect()
        resource_id: str | None = None
        try:
            resource = await resource_repository.create(
                ResourceCreate(
                    title="Atlas integration test resource",
                    type=ResourceType.NOTE,
                    content=(
                        "MongoDB Atlas Vector Search finds semantically similar text by "
                        "comparing embedding vectors with approximate nearest neighbor search."
                    ),
                )
            )
            resource_id = resource.id

            await processing_service.run_processing(resource_id)
            await embedding_service.run_embedding(resource_id)

            return await search_service.vector_search(
                VectorSearchRequest(query="how does semantic vector search work?", top_k=3)
            )
        finally:
            if resource_id:
                await chunk_repository.delete_by_resource(resource_id)
                await resource_repository.delete(resource_id)
            mongodb.close()

    response = asyncio.run(scenario())

    assert response.count > 0
    assert response.results[0].score > 0
    assert "vector search" in response.results[0].text.lower()
