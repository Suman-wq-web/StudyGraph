"""
Tests for POST /api/v1/search/vector (app/services/search_service.py). No
real Gemini calls and no real MongoDB Atlas $vectorSearch -- the embedding
provider and `chunk_repository.vector_search` are both mocked/injected, since
neither is available against the local test MongoDB (see docs/DATABASE.md,
"Atlas Vector Search setup").

Tests that need a resource in the database *and* call the async service layer
directly (not through the HTTP `client` fixture) open their own short-lived
Mongo connection bound to their own event loop -- mixing `TestClient` (which
owns its own loop-bound Motor client) with a bare `asyncio.run()` call in the
same test raises "attached to a different loop". See test_processing.py's
AlreadyProcessingError test for the same pattern.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.db import chunk_repository, mongodb, resource_repository
from app.models.embedding import VectorSearchRequest
from app.models.resource import ResourceCreate, ResourceType
from app.services import search_service
from app.services.rag.embeddings import EmbeddingProvider, EmbeddingProviderError, EmbeddingVector

_TEST_USER_ID = "test-search-user"


class FakeEmbeddingProvider(EmbeddingProvider):
    def __init__(self):
        self.queries: list[str] = []

    @property
    def model_name(self) -> str:
        return "fake-embedding-model"

    async def embed_documents(self, texts):
        raise NotImplementedError("not used by search")

    async def embed_query(self, text: str) -> EmbeddingVector:
        self.queries.append(text)
        return EmbeddingVector(values=[0.1, 0.2, 0.3], dimensions=3)


def _run_with_db(coro_fn):
    """Runs `coro_fn()` (a zero-arg coroutine function) inside a fresh event
    loop with its own Mongo connection, isolated from the `client` fixture's."""

    async def _wrapped():
        mongodb.connect()
        try:
            return await coro_fn()
        finally:
            mongodb.close()

    return asyncio.run(_wrapped())


def _create_resource(client: TestClient, **overrides) -> dict:
    payload = {"title": "Search test resource", "type": "note", "content": "hello", **overrides}
    response = client.post("/api/v1/resources", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


class TestRequestValidation:
    def test_empty_query_is_rejected(self, client: TestClient):
        response = client.post("/api/v1/search/vector", json={"query": ""})
        assert response.status_code == 422

    def test_missing_query_is_rejected(self, client: TestClient):
        response = client.post("/api/v1/search/vector", json={})
        assert response.status_code == 422

    def test_top_k_below_minimum_is_rejected(self, client: TestClient):
        response = client.post("/api/v1/search/vector", json={"query": "x", "topK": 0})
        assert response.status_code == 422

    def test_top_k_above_maximum_is_rejected(self, client: TestClient):
        response = client.post("/api/v1/search/vector", json={"query": "x", "topK": 51})
        assert response.status_code == 422

    def test_invalid_resource_type_is_rejected(self, client: TestClient):
        response = client.post(
            "/api/v1/search/vector", json={"query": "x", "resourceType": "podcast"}
        )
        assert response.status_code == 422

    def test_default_top_k_is_five(self):
        request = VectorSearchRequest(query="hello")
        assert request.top_k == 5


class TestSearchServiceWithMockedVectorSearch:
    def test_search_response_structure(self, monkeypatch):
        async def scenario():
            resource = await resource_repository.create(
                ResourceCreate(title="Neural networks 101", type=ResourceType.NOTE, content="x"),
                _TEST_USER_ID,
            )

            async def fake_vector_search(query_vector, *, top_k, resource_ids=None, num_candidates=None):
                assert query_vector == [0.1, 0.2, 0.3]
                return [
                    {
                        "id": "656565656565656565656565",
                        "resource_id": resource.id,
                        "chunk_index": 0,
                        "text": "Neural networks are composed of layers.",
                        "score": 0.87,
                    }
                ]

            monkeypatch.setattr(chunk_repository, "vector_search", fake_vector_search)

            return await search_service.vector_search(
                VectorSearchRequest(query="what are neural networks?"),
                _TEST_USER_ID,
                provider=FakeEmbeddingProvider(),
            ), resource

        result, resource = _run_with_db(scenario)

        assert result.query == "what are neural networks?"
        assert result.count == 1
        item = result.results[0]
        assert item.chunk_id == "656565656565656565656565"
        assert item.resource_id == resource.id
        assert item.resource_title == "Neural networks 101"
        assert item.resource_type == "note"
        assert item.chunk_index == 0
        assert item.text == "Neural networks are composed of layers."
        assert item.score == 0.87

    def test_no_results_from_vector_search_yields_empty_response(self, monkeypatch):
        async def fake_vector_search(*args, **kwargs):
            return []

        async def scenario():
            # A resource must exist for this user, or vector_search() would
            # short-circuit on the (now always-applied) user scope before
            # ever reaching the mock below -- see search_service.py.
            await resource_repository.create(
                ResourceCreate(title="Anything", type=ResourceType.NOTE, content="x"), _TEST_USER_ID
            )
            monkeypatch.setattr(chunk_repository, "vector_search", fake_vector_search)
            return await search_service.vector_search(
                VectorSearchRequest(query="anything"), _TEST_USER_ID, provider=FakeEmbeddingProvider()
            )

        result = _run_with_db(scenario)

        assert result.results == []
        assert result.count == 0

    def test_hit_for_a_deleted_resource_is_skipped(self, monkeypatch):
        async def fake_vector_search(*args, **kwargs):
            return [
                {
                    "id": "656565656565656565656565",
                    "resource_id": "000000000000000000000000",  # doesn't exist
                    "chunk_index": 0,
                    "text": "orphaned chunk",
                    "score": 0.5,
                }
            ]

        async def scenario():
            # Same reasoning as above: a resource must exist for this user
            # so the mock is actually reached.
            await resource_repository.create(
                ResourceCreate(title="Anything", type=ResourceType.NOTE, content="x"), _TEST_USER_ID
            )
            monkeypatch.setattr(chunk_repository, "vector_search", fake_vector_search)
            return await search_service.vector_search(
                VectorSearchRequest(query="anything"), _TEST_USER_ID, provider=FakeEmbeddingProvider()
            )

        result = _run_with_db(scenario)

        assert result.results == []
        assert result.count == 0


class TestMetadataFiltering:
    def test_type_filter_resolves_to_matching_resource_ids(self, monkeypatch):
        captured: dict = {}

        async def fake_vector_search(query_vector, *, top_k, resource_ids=None, num_candidates=None):
            captured["resource_ids"] = resource_ids
            return []

        async def scenario():
            note = await resource_repository.create(
                ResourceCreate(title="A note", type=ResourceType.NOTE, content="x"), _TEST_USER_ID
            )
            await resource_repository.create(
                ResourceCreate(
                    title="An article",
                    type=ResourceType.ARTICLE,
                    source_url="https://example.com",
                    content="x",
                ),
                _TEST_USER_ID,
            )
            monkeypatch.setattr(chunk_repository, "vector_search", fake_vector_search)
            await search_service.vector_search(
                VectorSearchRequest(query="x", resource_type="note"),
                _TEST_USER_ID,
                provider=FakeEmbeddingProvider(),
            )
            return note

        note = _run_with_db(scenario)
        assert captured["resource_ids"] == [note.id]

    def test_no_matching_resources_skips_vector_search_entirely(self, monkeypatch):
        called = False

        async def fake_vector_search(*args, **kwargs):
            nonlocal called
            called = True
            return []

        async def scenario():
            await resource_repository.create(
                ResourceCreate(title="A note", type=ResourceType.NOTE, content="x"), _TEST_USER_ID
            )
            monkeypatch.setattr(chunk_repository, "vector_search", fake_vector_search)
            return await search_service.vector_search(
                VectorSearchRequest(query="x", resource_type="video"),
                _TEST_USER_ID,
                provider=FakeEmbeddingProvider(),
            )

        result = _run_with_db(scenario)

        assert called is False
        assert result.count == 0

    def test_no_type_tag_filter_still_restricts_to_the_callers_own_resources(self, monkeypatch):
        """Phase 8: unlike Phase 4, "no filter" no longer means "search
        every user's chunks" -- the caller's own resource ids are always
        the outer bound, even with no explicit type/tag filter."""
        captured: dict = {}

        async def fake_vector_search(query_vector, *, top_k, resource_ids=None, num_candidates=None):
            captured["resource_ids"] = resource_ids
            return []

        async def scenario():
            note = await resource_repository.create(
                ResourceCreate(title="A note", type=ResourceType.NOTE, content="x"), _TEST_USER_ID
            )
            monkeypatch.setattr(chunk_repository, "vector_search", fake_vector_search)
            await search_service.vector_search(
                VectorSearchRequest(query="x"), _TEST_USER_ID, provider=FakeEmbeddingProvider()
            )
            return note

        note = _run_with_db(scenario)
        assert captured["resource_ids"] == [note.id]


class TestUnavailabilityHandling:
    def test_embedding_failure_raises_embedding_unavailable(self):
        class FailingProvider(FakeEmbeddingProvider):
            async def embed_query(self, text: str):
                raise EmbeddingProviderError("Gemini rejected the request")

        async def scenario():
            # A resource must exist for this user, or vector_search() would
            # short-circuit on the (now always-applied) user scope before
            # ever reaching the embedding call being tested here.
            await resource_repository.create(
                ResourceCreate(title="Anything", type=ResourceType.NOTE, content="x"), _TEST_USER_ID
            )
            await search_service.vector_search(
                VectorSearchRequest(query="x"), _TEST_USER_ID, provider=FailingProvider()
            )

        with pytest.raises(search_service.EmbeddingUnavailableError):
            _run_with_db(scenario)

    def test_vector_search_failure_raises_vector_search_unavailable(self, monkeypatch):
        async def broken_vector_search(*args, **kwargs):
            raise RuntimeError("$vectorSearch is not supported")

        async def scenario():
            await resource_repository.create(
                ResourceCreate(title="Anything", type=ResourceType.NOTE, content="x"), _TEST_USER_ID
            )
            monkeypatch.setattr(chunk_repository, "vector_search", broken_vector_search)
            await search_service.vector_search(
                VectorSearchRequest(query="x"), _TEST_USER_ID, provider=FakeEmbeddingProvider()
            )

        with pytest.raises(search_service.VectorSearchUnavailableError):
            _run_with_db(scenario)

    def test_api_returns_503_when_vector_search_unavailable(self, client: TestClient, monkeypatch):
        async def broken_vector_search(*args, **kwargs):
            raise RuntimeError("$vectorSearch is not supported")

        # A resource must exist for the authenticated caller, or the route
        # would short-circuit on the (now always-applied) user scope before
        # ever reaching $vectorSearch at all -- see search_service.py.
        _create_resource(client)

        monkeypatch.setattr(chunk_repository, "vector_search", broken_vector_search)
        monkeypatch.setattr(search_service, "get_embedding_provider", lambda: FakeEmbeddingProvider())

        response = client.post("/api/v1/search/vector", json={"query": "hello"})

        assert response.status_code == 503
