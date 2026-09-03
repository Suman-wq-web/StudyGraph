"""
Tests for app/db/chunk_repository.py:get_many_by_ids (Phase 5) -- a plain
`find` against the local test MongoDB, no Atlas features needed (unlike
vector_search/text_search, which require real Atlas indexes and are only
exercised via mocking elsewhere or the opt-in real-integration tests).
"""

import asyncio

from app.db import chunk_repository, mongodb, resource_repository
from app.models.resource import ResourceCreate, ResourceType
from app.services.ingestion.chunking import TextChunk

_TEST_USER_ID = "test-chunk-repo-user"


def _run_with_db(coro_fn):
    """Same pattern as test_search.py: isolates this test's Mongo connection
    on its own event loop, independent of the `client` fixture's."""

    async def _wrapped():
        mongodb.connect()
        try:
            return await coro_fn()
        finally:
            mongodb.close()

    return asyncio.run(_wrapped())


class TestGetManyByIds:
    def test_fetches_multiple_chunks_by_id(self):
        async def scenario():
            resource = await resource_repository.create(
                ResourceCreate(title="Chunk repo test", type=ResourceType.NOTE, content="x"),
                _TEST_USER_ID,
            )
            chunks = await chunk_repository.replace_chunks_for_resource(
                resource.id,
                [
                    TextChunk(text="first chunk", token_count=2, start_token=0, end_token=2),
                    TextChunk(text="second chunk", token_count=2, start_token=2, end_token=4),
                ],
                _TEST_USER_ID,
            )
            return chunks

        chunks = _run_with_db(scenario)
        ids = [chunk.id for chunk in chunks]

        result = _run_with_db(lambda: chunk_repository.get_many_by_ids(ids, _TEST_USER_ID))

        assert {c.text for c in result} == {"first chunk", "second chunk"}

    def test_skips_malformed_and_nonexistent_ids(self):
        result = _run_with_db(
            lambda: chunk_repository.get_many_by_ids(
                ["not-an-object-id", "000000000000000000000000"], _TEST_USER_ID
            )
        )
        assert result == []

    def test_empty_input_returns_empty_list_without_querying(self):
        result = _run_with_db(lambda: chunk_repository.get_many_by_ids([], _TEST_USER_ID))
        assert result == []
