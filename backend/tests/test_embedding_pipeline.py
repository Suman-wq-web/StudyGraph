"""
Tests for the embedding pipeline (app/services/embedding_service.py) and its
API endpoints. No real Gemini calls -- a FakeEmbeddingProvider test double
stands in wherever a provider is needed, either injected directly or via
monkeypatching `embedding_service.get_embedding_provider`.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.db import mongodb, resource_repository
from app.models.resource import ResourceCreate, ResourceType
from app.services import embedding_service, processing_service

_TEST_USER_ID = "test-embedding-user"
from app.services.rag.embeddings import (
    EmbeddingProvider,
    EmbeddingRateLimitError,
    EmbeddingVector,
)


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic in-memory stand-in: returns `[index] * dimensions` per
    text, optionally failing the first `fail_times` calls to exercise retry."""

    def __init__(self, *, dimensions: int = 8, fail_times: int = 0, error_cls=EmbeddingRateLimitError):
        self.calls: list[list[str]] = []
        self.dimensions = dimensions
        self._fail_times = fail_times
        self._error_cls = error_cls

    @property
    def model_name(self) -> str:
        return "fake-embedding-model"

    async def embed_documents(self, texts: list[str]) -> list[EmbeddingVector]:
        self.calls.append(list(texts))
        if self._fail_times > 0:
            self._fail_times -= 1
            raise self._error_cls("simulated failure")
        return [
            EmbeddingVector(values=[float(i)] * self.dimensions, dimensions=self.dimensions)
            for i in range(len(texts))
        ]

    async def embed_query(self, text: str) -> EmbeddingVector:
        return (await self.embed_documents([text]))[0]


def _create_and_process_note(client: TestClient, content: str | None = None) -> dict:
    payload = {
        "title": "Embedding pipeline test",
        "type": "note",
        "content": content or ("Sentence about StudyGraph. " * 30),
    }
    response = client.post("/api/v1/resources", json=payload)
    assert response.status_code == 201, response.text
    resource = response.json()
    process_response = client.post(f"/api/v1/resources/{resource['id']}/process")
    assert process_response.status_code == 202, process_response.text
    return client.get(f"/api/v1/resources/{resource['id']}").json()


class TestEmbedEndpointHappyPath:
    def test_embedding_a_chunked_resource_succeeds(self, client: TestClient, monkeypatch):
        fake = FakeEmbeddingProvider()
        monkeypatch.setattr(embedding_service, "get_embedding_provider", lambda: fake)

        resource = _create_and_process_note(client)
        response = client.post(f"/api/v1/resources/{resource['id']}/embed")
        assert response.status_code == 202
        assert response.json()["status"] == "embedding"

        status_response = client.get(f"/api/v1/resources/{resource['id']}/embedding-status")
        body = status_response.json()
        assert body["status"] == "embedded"
        assert body["embeddedChunkCount"] == body["totalChunkCount"]
        assert body["totalChunkCount"] > 0
        assert body["processingError"] is None

    def test_embedding_does_not_alter_chunk_text_or_order(self, client: TestClient, monkeypatch, chunks_collection):
        fake = FakeEmbeddingProvider()
        monkeypatch.setattr(embedding_service, "get_embedding_provider", lambda: fake)

        resource = _create_and_process_note(client)
        before = list(chunks_collection.find({"resource_id": resource["id"]}).sort("chunk_index", 1))

        client.post(f"/api/v1/resources/{resource['id']}/embed")

        after = list(chunks_collection.find({"resource_id": resource["id"]}).sort("chunk_index", 1))
        assert [c["text"] for c in before] == [c["text"] for c in after]
        assert [c["token_count"] for c in before] == [c["token_count"] for c in after]
        assert [c["chunk_index"] for c in before] == [c["chunk_index"] for c in after]
        assert all(c["embedding"] is None for c in before)
        assert all(c["embedding"] is not None for c in after)

    def test_stored_embedding_dimensions_match_provider_response(
        self, client: TestClient, monkeypatch, chunks_collection
    ):
        fake = FakeEmbeddingProvider(dimensions=17)
        monkeypatch.setattr(embedding_service, "get_embedding_provider", lambda: fake)

        resource = _create_and_process_note(client)
        client.post(f"/api/v1/resources/{resource['id']}/embed")

        stored = list(chunks_collection.find({"resource_id": resource["id"]}))
        assert all(len(c["embedding"]) == 17 for c in stored)


class TestEmbedEndpointErrors:
    def test_embed_missing_resource_returns_404(self, client: TestClient):
        response = client.post("/api/v1/resources/000000000000000000000000/embed")
        assert response.status_code == 404

    def test_embedding_status_missing_resource_returns_404(self, client: TestClient):
        response = client.get("/api/v1/resources/000000000000000000000000/embedding-status")
        assert response.status_code == 404

    def test_embed_before_processing_returns_409(self, client: TestClient):
        create_response = client.post(
            "/api/v1/resources", json={"title": "Not processed yet", "type": "note", "content": "hi"}
        )
        resource = create_response.json()

        response = client.post(f"/api/v1/resources/{resource['id']}/embed")
        assert response.status_code == 409

    def test_embed_without_configured_provider_fails_cleanly(self, client: TestClient, monkeypatch):
        # No GEMINI_API_KEY in the test environment -- exercises the real
        # (unmocked) provider-construction failure path end-to-end.
        monkeypatch.setattr("app.config.settings.gemini_api_key", "")
        resource = _create_and_process_note(client)

        client.post(f"/api/v1/resources/{resource['id']}/embed")

        status_response = client.get(f"/api/v1/resources/{resource['id']}/embedding-status")
        body = status_response.json()
        assert body["status"] == "failed"
        assert "GEMINI_API_KEY" in body["processingError"]


class TestIdempotentReembedding:
    def test_reembedding_skips_already_embedded_chunks(self, client: TestClient, monkeypatch):
        fake = FakeEmbeddingProvider()
        monkeypatch.setattr(embedding_service, "get_embedding_provider", lambda: fake)

        resource = _create_and_process_note(client)
        client.post(f"/api/v1/resources/{resource['id']}/embed")
        calls_after_first_run = len(fake.calls)
        assert calls_after_first_run > 0

        client.post(f"/api/v1/resources/{resource['id']}/embed")

        # Nothing left unembedded, so the second run should not call the
        # provider again at all.
        assert len(fake.calls) == calls_after_first_run

    def test_already_embedding_guard(self):
        """
        TestClient runs BackgroundTasks synchronously, so there's no real
        window where an HTTP round-trip observes EMBEDDING -- this exercises
        the service-layer guard directly (with its own Mongo connection,
        bound to its own event loop, independent of the `client` fixture's),
        the same technique used for the Phase 3 AlreadyProcessingError test.
        """

        async def _scenario() -> bool:
            mongodb.connect()
            try:
                resource = await resource_repository.create(
                    ResourceCreate(title="Guard test", type=ResourceType.NOTE, content="hello world"),
                    _TEST_USER_ID,
                )
                await processing_service.run_processing(resource.id, _TEST_USER_ID)
                await embedding_service.start_embedding(resource.id, _TEST_USER_ID)  # -> EMBEDDING
                try:
                    await embedding_service.start_embedding(resource.id, _TEST_USER_ID)
                    return False
                except embedding_service.AlreadyEmbeddingError:
                    return True
            finally:
                mongodb.close()

        assert asyncio.run(_scenario())


class TestRetryAndFailureHandling:
    def test_transient_failures_are_retried_and_eventually_succeed(self, monkeypatch):
        monkeypatch.setattr(embedding_service.asyncio, "sleep", _instant_sleep)
        fake = FakeEmbeddingProvider(fail_times=2)  # MAX_ATTEMPTS is 3, so this should succeed

        result = asyncio.run(embedding_service._embed_with_retry(fake, ["a", "b"]))

        assert len(result) == 2
        assert len(fake.calls) == 3  # 2 failures + 1 success

    def test_exhausting_retries_raises_provider_error(self, monkeypatch):
        monkeypatch.setattr(embedding_service.asyncio, "sleep", _instant_sleep)
        fake = FakeEmbeddingProvider(fail_times=10)  # never succeeds within MAX_ATTEMPTS

        with pytest.raises(embedding_service.EmbeddingProviderError):
            asyncio.run(embedding_service._embed_with_retry(fake, ["a"]))

    def test_permanent_failure_marks_resource_failed_without_storing_partial_embeddings(
        self, client: TestClient, monkeypatch, chunks_collection
    ):
        monkeypatch.setattr(embedding_service.asyncio, "sleep", _instant_sleep)
        fake = FakeEmbeddingProvider(fail_times=10)
        monkeypatch.setattr(embedding_service, "get_embedding_provider", lambda: fake)

        resource = _create_and_process_note(client)
        client.post(f"/api/v1/resources/{resource['id']}/embed")

        status_body = client.get(f"/api/v1/resources/{resource['id']}/embedding-status").json()
        assert status_body["status"] == "failed"
        assert status_body["embeddedChunkCount"] == 0

        stored = list(chunks_collection.find({"resource_id": resource["id"]}))
        assert all(c["embedding"] is None for c in stored)


class TestRetryDelayHandling:
    def test_retry_honors_gemini_retry_delay_when_present(self, monkeypatch):
        sleep_calls: list[float] = []
        monkeypatch.setattr(embedding_service.asyncio, "sleep", _recording_sleep(sleep_calls))
        fake = FakeEmbeddingProvider(fail_times=1)
        fake._error_cls = lambda message: EmbeddingRateLimitError(
            message, retry_delay_seconds=7.0
        )

        asyncio.run(embedding_service._embed_with_retry(fake, ["a"]))

        assert sleep_calls == [7.0]

    def test_retry_delay_is_capped_at_the_configured_maximum(self, monkeypatch):
        sleep_calls: list[float] = []
        monkeypatch.setattr(embedding_service.asyncio, "sleep", _recording_sleep(sleep_calls))
        fake = FakeEmbeddingProvider(fail_times=1)
        fake._error_cls = lambda message: EmbeddingRateLimitError(
            message, retry_delay_seconds=embedding_service.MAX_RETRY_DELAY_SECONDS + 100
        )

        asyncio.run(embedding_service._embed_with_retry(fake, ["a"]))

        assert sleep_calls == [embedding_service.MAX_RETRY_DELAY_SECONDS]

    def test_retry_falls_back_to_exponential_backoff_without_a_retry_delay(self, monkeypatch):
        sleep_calls: list[float] = []
        monkeypatch.setattr(embedding_service.asyncio, "sleep", _recording_sleep(sleep_calls))
        fake = FakeEmbeddingProvider(fail_times=2)  # plain EmbeddingRateLimitError, no retry_delay_seconds

        asyncio.run(embedding_service._embed_with_retry(fake, ["a", "b"]))

        assert sleep_calls == [
            embedding_service.BASE_BACKOFF_SECONDS * 1,
            embedding_service.BASE_BACKOFF_SECONDS * 2,
        ]


def _recording_sleep(sleep_calls: list[float]):
    async def _sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    return _sleep


async def _instant_sleep(_seconds: float) -> None:
    return None
