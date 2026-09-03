"""
Opt-in integration test that makes a REAL call to the Gemini embeddings API.
Skipped by default -- every other test in this suite mocks the provider (see
test_embeddings.py); this one exists to verify the actual SDK usage against
the real service when a developer explicitly wants that.

Enable with:
    RUN_GEMINI_INTEGRATION_TESTS=1 GEMINI_API_KEY=<real key> \\
    pytest tests/test_gemini_integration.py
"""

import asyncio
import os

import pytest

from app.services.rag.embeddings import GeminiEmbeddingProvider

_RUN = os.environ.get("RUN_GEMINI_INTEGRATION_TESTS") == "1"
_API_KEY = os.environ.get("GEMINI_API_KEY", "")

pytestmark = pytest.mark.skipif(
    not _RUN or not _API_KEY,
    reason="Set RUN_GEMINI_INTEGRATION_TESTS=1 and a real GEMINI_API_KEY to run this test.",
)


def test_real_gemini_embedding_call_returns_a_usable_vector():
    provider = GeminiEmbeddingProvider(api_key=_API_KEY, model="gemini-embedding-001")

    result = asyncio.run(
        provider.embed_documents(["StudyGraph is a personal learning knowledge graph."])
    )

    assert len(result) == 1
    assert result[0].dimensions > 0
    assert len(result[0].values) == result[0].dimensions
    assert all(isinstance(v, float) for v in result[0].values)


def test_real_gemini_query_and_document_embeddings_are_similar_for_related_text():
    provider = GeminiEmbeddingProvider(api_key=_API_KEY, model="gemini-embedding-001")

    async def scenario():
        query = await provider.embed_query("What is a knowledge graph?")
        [related] = await provider.embed_documents(
            ["A knowledge graph represents concepts and the relationships between them."]
        )
        [unrelated] = await provider.embed_documents(["Bananas are a good source of potassium."])
        return query, related, unrelated

    query, related, unrelated = asyncio.run(scenario())

    def cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        return dot / (norm_a * norm_b)

    assert cosine(query.values, related.values) > cosine(query.values, unrelated.values)
