"""
Opt-in END-TO-END integration test: real Gemini embeddings, real Gemini
generation, and a real MongoDB Atlas cluster with `document_chunks_vector_index`
provisioned (see docs/DATABASE.md, "Atlas Vector Search setup"). Ideally
`document_chunks_text_search` (see "Atlas Search (BM25) setup") is also
provisioned so hybrid retrieval exercises both branches -- but
app/services/rag/retrieval.py degrades gracefully to vector-only if the BM25
index isn't there yet (see test_retrieval.py's TestPartialFailureHandling),
so this test can still pass on vector search alone. Skipped by default.

Uses a NEW flag (RUN_RAG_CHAT_INTEGRATION_TESTS) rather than reusing
RUN_ATLAS_VECTOR_SEARCH_TESTS, since this additionally makes a real Gemini
*generation* call (not just embeddings) -- a distinct, heavier capability a
developer may not have opted into yet.

Enable with:
    RUN_RAG_CHAT_INTEGRATION_TESTS=1 GEMINI_API_KEY=<real key> \\
    MONGODB_URI=<Atlas SRV string> pytest tests/test_rag_chat_integration.py

Creates and deletes its own resource/chunks -- leaves no data behind, even on
failure (best-effort cleanup in a `finally`).
"""

import asyncio
import os

import pytest

from app.db import chunk_repository, mongodb, resource_repository
from app.models.resource import ResourceCreate, ResourceType
from app.services import embedding_service, processing_service
from app.services.rag import pipeline

_RUN = os.environ.get("RUN_RAG_CHAT_INTEGRATION_TESTS") == "1"
_API_KEY = os.environ.get("GEMINI_API_KEY", "")

pytestmark = pytest.mark.skipif(
    not _RUN or not _API_KEY,
    reason=(
        "Set RUN_RAG_CHAT_INTEGRATION_TESTS=1, a real GEMINI_API_KEY, and MONGODB_URI pointing "
        "at an Atlas cluster with document_chunks_vector_index provisioned to run this."
    ),
)


def test_real_end_to_end_rag_chat_answer_with_citations():
    async def scenario():
        mongodb.connect()
        resource_id: str | None = None
        try:
            resource = await resource_repository.create(
                ResourceCreate(
                    title="RAG chat integration test resource",
                    type=ResourceType.NOTE,
                    content=(
                        "The mitochondrion is the organelle that generates most of a cell's "
                        "supply of adenosine triphosphate (ATP), used as a source of chemical "
                        "energy. It is often called the powerhouse of the cell."
                    ),
                )
            )
            resource_id = resource.id

            await processing_service.run_processing(resource_id)
            await embedding_service.run_embedding(resource_id)

            return await pipeline.answer_query(
                pipeline.DEFAULT_USER_ID, "What does the mitochondrion do?"
            )
        finally:
            if resource_id:
                await chunk_repository.delete_by_resource(resource_id)
                await resource_repository.delete(resource_id)
            mongodb.close()

    response = asyncio.run(scenario())

    assert response.answer.strip()
    assert len(response.citations) > 0
    assert "mitochondrion" in response.citations[0].snippet.lower()
