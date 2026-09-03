"""
Tests for app/services/rag/citations.py:build_citations. Runs against the
local test MongoDB directly (no Atlas features needed -- this only joins
resource metadata via resource_repository.get_many_by_ids, a plain `find`).
"""

import asyncio

from app.db import mongodb, resource_repository
from app.models.resource import ResourceCreate, ResourceType
from app.services.ingestion.chunking import TextChunk
from app.services.rag import citations
from app.db import chunk_repository

_TEST_USER_ID = "test-citations-user"


def _run_with_db(coro_fn):
    async def _wrapped():
        mongodb.connect()
        try:
            return await coro_fn()
        finally:
            mongodb.close()

    return asyncio.run(_wrapped())


class TestSnippetTruncation:
    def test_short_text_is_returned_unchanged(self):
        assert citations._snippet("hello world", max_chars=320) == "hello world"

    def test_text_at_exact_limit_is_unchanged(self):
        text = "x" * 320
        assert citations._snippet(text, max_chars=320) == text

    def test_long_text_is_truncated_at_word_boundary_with_ellipsis(self):
        text = ("word " * 100).strip()  # 500 chars, well past 320
        snippet = citations._snippet(text, max_chars=320)

        assert len(snippet) <= 324  # 320 + "..." plus a little slack
        assert snippet.endswith("...")
        assert not snippet[:-3].endswith(" ")  # trimmed trailing space before "..."
        assert "word" in snippet


class TestBuildCitations:
    def test_empty_chunks_returns_empty_list(self):
        result = asyncio.run(citations.build_citations([], _TEST_USER_ID))
        assert result == []

    def test_one_citation_per_chunk_in_order_with_resource_metadata(self):
        async def scenario():
            resource = await resource_repository.create(
                ResourceCreate(title="Gradient Descent Notes", type=ResourceType.NOTE, content="x"),
                _TEST_USER_ID,
            )
            chunks = await chunk_repository.replace_chunks_for_resource(
                resource.id,
                [
                    TextChunk(text="first chunk text", token_count=3, start_token=0, end_token=3),
                    TextChunk(text="second chunk text", token_count=3, start_token=3, end_token=6),
                ],
                _TEST_USER_ID,
            )
            return chunks, resource

        chunks, resource = _run_with_db(scenario)

        result = _run_with_db(lambda: citations.build_citations(chunks, _TEST_USER_ID))

        assert len(result) == 2
        assert [c.chunk_id for c in result] == [chunk.id for chunk in chunks]
        assert [c.snippet for c in result] == ["first chunk text", "second chunk text"]
        assert [c.chunk_index for c in result] == [0, 1]
        for citation in result:
            assert citation.resource_id == resource.id
            assert citation.resource_title == "Gradient Descent Notes"
            assert citation.resource_type == ResourceType.NOTE
            assert citation.score == 0.0  # default; pipeline.retrieve_context attaches the real score

    def test_chunk_with_deleted_resource_is_skipped(self):
        async def scenario():
            resource = await resource_repository.create(
                ResourceCreate(title="Temp resource", type=ResourceType.NOTE, content="x"),
                _TEST_USER_ID,
            )
            chunks = await chunk_repository.replace_chunks_for_resource(
                resource.id,
                [TextChunk(text="orphaned chunk", token_count=2, start_token=0, end_token=2)],
                _TEST_USER_ID,
            )
            await resource_repository.delete(resource.id, _TEST_USER_ID)
            return chunks

        chunks = _run_with_db(scenario)

        result = _run_with_db(lambda: citations.build_citations(chunks, _TEST_USER_ID))

        assert result == []
