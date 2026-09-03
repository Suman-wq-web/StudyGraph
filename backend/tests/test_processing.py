import asyncio

from fastapi.testclient import TestClient

from app.config import settings
from app.db import mongodb, resource_repository
from app.models.resource import ResourceCreate, ResourceType
from app.services import embedding_service, processing_service
from app.services.ingestion.url_extraction import UrlExtractionResult
from app.services.ingestion.youtube_transcript import TranscriptResult
from app.services.rag.embeddings import EmbeddingProvider, EmbeddingRateLimitError, EmbeddingVector

_TEST_USER_ID = "test-processing-user"


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic in-memory stand-in for the auto-embed tests below --
    mirrors tests/test_embedding_pipeline.py's own FakeEmbeddingProvider
    (kept local rather than imported, matching this suite's convention of
    self-contained test modules). Returns `[index] * dimensions` per text,
    optionally failing the first `fail_times` calls."""

    def __init__(self, *, dimensions: int = 8, fail_times: int = 0):
        self.calls: list[list[str]] = []
        self.dimensions = dimensions
        self._fail_times = fail_times

    @property
    def model_name(self) -> str:
        return "fake-embedding-model"

    async def embed_documents(self, texts: list[str]) -> list[EmbeddingVector]:
        self.calls.append(list(texts))
        if self._fail_times > 0:
            self._fail_times -= 1
            raise EmbeddingRateLimitError("simulated failure")
        return [
            EmbeddingVector(values=[float(i)] * self.dimensions, dimensions=self.dimensions)
            for i in range(len(texts))
        ]

    async def embed_query(self, text: str) -> EmbeddingVector:
        return (await self.embed_documents([text]))[0]


async def _instant_sleep(_seconds: float) -> None:
    return None


def _create_resource(client: TestClient, **overrides) -> dict:
    payload = {
        "title": "Processing test resource",
        "type": "note",
        "content": "This is the stored content that should be chunked. " * 5,
        **overrides,
    }
    response = client.post("/api/v1/resources", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


class TestProcessNoteAndArticle:
    def test_process_note_completes_and_creates_chunks(self, client: TestClient, chunks_collection):
        resource = _create_resource(client, type="note", sourceUrl=None)

        response = client.post(f"/api/v1/resources/{resource['id']}/process")
        assert response.status_code == 202, response.text
        assert response.json()["status"] == "processing"

        status_response = client.get(f"/api/v1/resources/{resource['id']}/processing-status")
        assert status_response.status_code == 200
        body = status_response.json()
        assert body["status"] == "ready"
        assert body["chunkCount"] > 0
        assert body["processingError"] is None

        stored = list(chunks_collection.find({"resource_id": resource["id"]}))
        assert len(stored) == body["chunkCount"]
        assert all(doc["text"].strip() for doc in stored)
        assert [doc["chunk_index"] for doc in stored] == list(range(len(stored)))

    def test_process_article_with_content_completes(self, client: TestClient):
        resource = _create_resource(
            client, type="article", sourceUrl="https://example.com/post", content="Article body text."
        )
        client.post(f"/api/v1/resources/{resource['id']}/process")

        status_response = client.get(f"/api/v1/resources/{resource['id']}/processing-status")
        body = status_response.json()
        assert body["status"] == "ready"
        assert body["chunkCount"] == 1

    def test_processed_resource_reflects_ready_status_on_get(self, client: TestClient):
        resource = _create_resource(client, type="note", sourceUrl=None)
        client.post(f"/api/v1/resources/{resource['id']}/process")

        fetched = client.get(f"/api/v1/resources/{resource['id']}").json()
        assert fetched["status"] == "ready"
        assert fetched["processingError"] is None
        # everything else about the resource is untouched by processing
        assert fetched["title"] == resource["title"]
        assert fetched["content"] == resource["content"]


class TestProcessWithoutExtractableContent:
    def test_process_url_without_source_or_content_fails_clearly(self, client: TestClient):
        resource = _create_resource(client, type="url", sourceUrl=None, content=None)
        client.post(f"/api/v1/resources/{resource['id']}/process")

        status_response = client.get(f"/api/v1/resources/{resource['id']}/processing-status")
        body = status_response.json()
        assert body["status"] == "failed"
        assert body["chunkCount"] == 0
        assert body["processingError"]

    def test_process_url_with_unreadable_page_and_no_manual_content_fails_clearly(
        self, client: TestClient, monkeypatch
    ):
        """A URL that fetches but yields no usable text (e.g. an empty page)
        surfaces url_extraction's own clear error rather than the old,
        now-obsolete 'not implemented' message -- see
        app/services/ingestion/url_extraction.py."""

        async def fake_fetch_url_content(source_url):
            assert source_url == "https://example.com/empty"
            return UrlExtractionResult(text=None, error="No readable article/page text could be extracted.")

        monkeypatch.setattr(processing_service, "fetch_url_content", fake_fetch_url_content)

        resource = _create_resource(
            client, type="url", sourceUrl="https://example.com/empty", content=None
        )
        client.post(f"/api/v1/resources/{resource['id']}/process")

        status_response = client.get(f"/api/v1/resources/{resource['id']}/processing-status")
        body = status_response.json()
        assert body["status"] == "failed"
        assert body["chunkCount"] == 0
        assert "no readable" in body["processingError"].lower()

    def test_process_video_without_content_fails_clearly(self, client: TestClient):
        resource = _create_resource(
            client, type="video", sourceUrl="https://example.com/watch", content=None
        )
        client.post(f"/api/v1/resources/{resource['id']}/process")

        status_response = client.get(f"/api/v1/resources/{resource['id']}/processing-status")
        body = status_response.json()
        assert body["status"] == "failed"
        assert "transcript" in body["processingError"].lower()

    def test_process_note_without_content_fails_clearly(self, client: TestClient):
        resource = _create_resource(client, type="note", sourceUrl=None, content=None)
        client.post(f"/api/v1/resources/{resource['id']}/process")

        status_response = client.get(f"/api/v1/resources/{resource['id']}/processing-status")
        body = status_response.json()
        assert body["status"] == "failed"
        assert body["processingError"]


class TestProcessVideoTranscript:
    """Video resources fetch their transcript via
    app/services/ingestion/youtube_transcript.py (monkeypatched here so no
    real network call is made) before the shared chunk/embed/extract
    pipeline runs -- see app/services/processing_service.py."""

    def test_process_video_with_available_transcript_completes_and_creates_chunks(
        self, client: TestClient, chunks_collection, monkeypatch
    ):
        async def fake_fetch_transcript(source_url):
            assert source_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            return TranscriptResult(text="This is the automatically fetched transcript text. " * 5)

        monkeypatch.setattr(processing_service, "fetch_transcript", fake_fetch_transcript)

        resource = _create_resource(
            client,
            type="video",
            sourceUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            content=None,
        )
        response = client.post(f"/api/v1/resources/{resource['id']}/process")
        assert response.status_code == 202, response.text

        status_response = client.get(f"/api/v1/resources/{resource['id']}/processing-status")
        body = status_response.json()
        assert body["status"] == "ready"
        assert body["chunkCount"] > 0
        assert body["processingError"] is None

        stored = list(chunks_collection.find({"resource_id": resource["id"]}))
        assert any("automatically fetched transcript" in doc["text"] for doc in stored)

    def test_process_video_with_unavailable_transcript_and_no_manual_content_fails_clearly(
        self, client: TestClient, monkeypatch
    ):
        async def fake_fetch_transcript(source_url):
            return TranscriptResult(
                text=None,
                error="A transcript is not available for this video (captions may be disabled).",
            )

        monkeypatch.setattr(processing_service, "fetch_transcript", fake_fetch_transcript)

        resource = _create_resource(
            client,
            type="video",
            sourceUrl="https://www.youtube.com/watch?v=unavailable123",
            content=None,
        )
        client.post(f"/api/v1/resources/{resource['id']}/process")

        status_response = client.get(f"/api/v1/resources/{resource['id']}/processing-status")
        body = status_response.json()
        assert body["status"] == "failed"
        assert body["chunkCount"] == 0
        assert "transcript" in body["processingError"].lower()
        assert "not implemented" not in body["processingError"].lower()

    def test_process_video_falls_back_to_manual_transcript_when_fetch_fails(
        self, client: TestClient, chunks_collection, monkeypatch
    ):
        async def fake_fetch_transcript(source_url):
            return TranscriptResult(text=None, error="Transcripts are disabled for this video.")

        monkeypatch.setattr(processing_service, "fetch_transcript", fake_fetch_transcript)

        resource = _create_resource(
            client,
            type="video",
            sourceUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            content="Manually pasted transcript text. " * 5,
        )
        client.post(f"/api/v1/resources/{resource['id']}/process")

        status_response = client.get(f"/api/v1/resources/{resource['id']}/processing-status")
        body = status_response.json()
        assert body["status"] == "ready"
        assert body["chunkCount"] > 0

    def test_reprocessing_a_video_refetches_the_transcript(
        self, client: TestClient, chunks_collection, monkeypatch
    ):
        """The 'Reprocess' action re-runs the whole pipeline, including the
        transcript fetch -- a video that failed once (e.g. captions weren't
        ready yet) can succeed on reprocess without any code path other than
        the normal /process route."""
        call_count = {"n": 0}

        async def fake_fetch_transcript(source_url):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return TranscriptResult(text=None, error="A transcript is not available yet.")
            return TranscriptResult(text="Transcript now available. " * 10)

        monkeypatch.setattr(processing_service, "fetch_transcript", fake_fetch_transcript)

        resource = _create_resource(
            client,
            type="video",
            sourceUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            content=None,
        )

        client.post(f"/api/v1/resources/{resource['id']}/process")
        first_status = client.get(f"/api/v1/resources/{resource['id']}/processing-status").json()
        assert first_status["status"] == "failed"

        reprocess_response = client.post(f"/api/v1/resources/{resource['id']}/process")
        assert reprocess_response.status_code == 202

        second_status = client.get(f"/api/v1/resources/{resource['id']}/processing-status").json()
        assert second_status["status"] == "ready"
        assert second_status["chunkCount"] > 0
        assert call_count["n"] == 2


class TestProcessUrlYoutubeTranscript:
    """A URL resource whose source_url is a YouTube link is routed through
    the same transcript fetch as a Video resource (monkeypatched here so no
    real network call is made) -- see app/services/processing_service.py.
    Non-YouTube URLs are instead routed through the generic HTML/PDF
    fetcher, covered by TestProcessUrlGenericExtraction below."""

    def test_process_url_with_youtube_link_and_available_transcript_completes_and_creates_chunks(
        self, client: TestClient, chunks_collection, monkeypatch
    ):
        async def fake_fetch_transcript(source_url):
            assert source_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            return TranscriptResult(text="This is the automatically fetched transcript text. " * 5)

        monkeypatch.setattr(processing_service, "fetch_transcript", fake_fetch_transcript)

        resource = _create_resource(
            client,
            type="url",
            sourceUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            content=None,
        )
        response = client.post(f"/api/v1/resources/{resource['id']}/process")
        assert response.status_code == 202, response.text

        status_response = client.get(f"/api/v1/resources/{resource['id']}/processing-status")
        body = status_response.json()
        assert body["status"] == "ready"
        assert body["chunkCount"] > 0
        assert body["processingError"] is None

        stored = list(chunks_collection.find({"resource_id": resource["id"]}))
        assert any("automatically fetched transcript" in doc["text"] for doc in stored)

    def test_process_url_with_youtube_link_and_unavailable_transcript_fails_clearly(
        self, client: TestClient, monkeypatch
    ):
        async def fake_fetch_transcript(source_url):
            return TranscriptResult(
                text=None,
                error="A transcript is not available for this video (captions may be disabled).",
            )

        monkeypatch.setattr(processing_service, "fetch_transcript", fake_fetch_transcript)

        resource = _create_resource(
            client,
            type="url",
            sourceUrl="https://www.youtube.com/watch?v=unavailable",
            content=None,
        )
        client.post(f"/api/v1/resources/{resource['id']}/process")

        status_response = client.get(f"/api/v1/resources/{resource['id']}/processing-status")
        body = status_response.json()
        assert body["status"] == "failed"
        assert body["chunkCount"] == 0
        assert "transcript" in body["processingError"].lower()
        assert "not implemented" not in body["processingError"].lower()

    def test_process_url_non_youtube_link_does_not_attempt_transcript_fetch(
        self, client: TestClient, monkeypatch
    ):
        async def fail_if_called(source_url):
            raise AssertionError("fetch_transcript should not be called for non-YouTube URLs")

        async def fake_fetch_url_content(source_url):
            return UrlExtractionResult(text="Generic extraction result text. " * 5)

        monkeypatch.setattr(processing_service, "fetch_transcript", fail_if_called)
        monkeypatch.setattr(processing_service, "fetch_url_content", fake_fetch_url_content)

        resource = _create_resource(
            client, type="url", sourceUrl="https://example.com/article", content=None
        )
        response = client.post(f"/api/v1/resources/{resource['id']}/process")
        assert response.status_code == 202

        status_response = client.get(f"/api/v1/resources/{resource['id']}/processing-status")
        body = status_response.json()
        assert body["status"] == "ready"


class TestProcessUrlGenericExtraction:
    """A URL resource whose source_url is NOT a YouTube link is routed
    through the generic HTML/PDF fetcher/extractor
    (app/services/ingestion/url_extraction.py, monkeypatched here so no
    real network call is made) -- see app/services/processing_service.py.
    YouTube links are covered by TestProcessUrlYoutubeTranscript above."""

    def test_process_url_with_extracted_webpage_text_completes_and_creates_chunks(
        self, client: TestClient, chunks_collection, monkeypatch
    ):
        async def fake_fetch_url_content(source_url):
            assert source_url == "https://example.com/article"
            return UrlExtractionResult(text="This is the automatically extracted webpage text. " * 5)

        monkeypatch.setattr(processing_service, "fetch_url_content", fake_fetch_url_content)

        resource = _create_resource(
            client, type="url", sourceUrl="https://example.com/article", content=None
        )
        response = client.post(f"/api/v1/resources/{resource['id']}/process")
        assert response.status_code == 202, response.text

        status_response = client.get(f"/api/v1/resources/{resource['id']}/processing-status")
        body = status_response.json()
        assert body["status"] == "ready"
        assert body["chunkCount"] > 0
        assert body["processingError"] is None

        stored = list(chunks_collection.find({"resource_id": resource["id"]}))
        assert any("automatically extracted webpage text" in doc["text"] for doc in stored)

    def test_process_url_with_unreadable_page_and_no_manual_content_fails_clearly(
        self, client: TestClient, monkeypatch
    ):
        async def fake_fetch_url_content(source_url):
            return UrlExtractionResult(
                text=None, error="No readable article/page text could be extracted from this URL."
            )

        monkeypatch.setattr(processing_service, "fetch_url_content", fake_fetch_url_content)

        resource = _create_resource(
            client, type="url", sourceUrl="https://example.com/empty-page", content=None
        )
        client.post(f"/api/v1/resources/{resource['id']}/process")

        status_response = client.get(f"/api/v1/resources/{resource['id']}/processing-status")
        body = status_response.json()
        assert body["status"] == "failed"
        assert body["chunkCount"] == 0
        assert "no readable" in body["processingError"].lower()

    def test_process_url_falls_back_to_manual_content_when_extraction_fails(
        self, client: TestClient, chunks_collection, monkeypatch
    ):
        async def fake_fetch_url_content(source_url):
            return UrlExtractionResult(text=None, error="This URL could not be fetched.")

        monkeypatch.setattr(processing_service, "fetch_url_content", fake_fetch_url_content)

        resource = _create_resource(
            client,
            type="url",
            sourceUrl="https://example.com/unreachable",
            content="Manually pasted article text. " * 5,
        )
        client.post(f"/api/v1/resources/{resource['id']}/process")

        status_response = client.get(f"/api/v1/resources/{resource['id']}/processing-status")
        body = status_response.json()
        assert body["status"] == "ready"
        assert body["chunkCount"] > 0

    def test_process_url_localhost_is_rejected_without_any_network_call(self, client: TestClient):
        """No monkeypatching here -- validate_fetchable_url's SSRF guard
        rejects this before url_extraction ever attempts a real request,
        so this exercises the real code path end-to-end."""
        resource = _create_resource(
            client, type="url", sourceUrl="http://127.0.0.1:9999/secret", content=None
        )
        client.post(f"/api/v1/resources/{resource['id']}/process")

        status_response = client.get(f"/api/v1/resources/{resource['id']}/processing-status")
        body = status_response.json()
        assert body["status"] == "failed"
        assert "local" in body["processingError"].lower() or "internal" in body["processingError"].lower()

    def test_reprocessing_a_url_refetches_the_page(
        self, client: TestClient, chunks_collection, monkeypatch
    ):
        call_count = {"n": 0}

        async def fake_fetch_url_content(source_url):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return UrlExtractionResult(text=None, error="This URL could not be fetched.")
            return UrlExtractionResult(text="Page content now available. " * 10)

        monkeypatch.setattr(processing_service, "fetch_url_content", fake_fetch_url_content)

        resource = _create_resource(
            client, type="url", sourceUrl="https://example.com/flaky", content=None
        )

        client.post(f"/api/v1/resources/{resource['id']}/process")
        first_status = client.get(f"/api/v1/resources/{resource['id']}/processing-status").json()
        assert first_status["status"] == "failed"

        reprocess_response = client.post(f"/api/v1/resources/{resource['id']}/process")
        assert reprocess_response.status_code == 202

        second_status = client.get(f"/api/v1/resources/{resource['id']}/processing-status").json()
        assert second_status["status"] == "ready"
        assert second_status["chunkCount"] > 0
        assert call_count["n"] == 2


class TestReprocessingIdempotency:
    def test_reprocessing_replaces_rather_than_duplicates_chunks(
        self, client: TestClient, chunks_collection
    ):
        resource = _create_resource(client, type="note", sourceUrl=None)

        client.post(f"/api/v1/resources/{resource['id']}/process")
        first_count = chunks_collection.count_documents({"resource_id": resource["id"]})
        assert first_count > 0

        client.post(f"/api/v1/resources/{resource['id']}/process")
        second_count = chunks_collection.count_documents({"resource_id": resource["id"]})

        assert second_count == first_count

    def test_reprocessing_after_content_edit_reflects_new_content(
        self, client: TestClient, chunks_collection
    ):
        resource = _create_resource(client, type="note", sourceUrl=None, content="short")
        client.post(f"/api/v1/resources/{resource['id']}/process")

        client.patch(f"/api/v1/resources/{resource['id']}", json={"content": "a much longer piece of content " * 20})
        client.post(f"/api/v1/resources/{resource['id']}/process")

        stored = list(chunks_collection.find({"resource_id": resource["id"]}))
        combined_text = " ".join(doc["text"] for doc in stored)
        assert "much longer piece of content" in combined_text
        assert "short" not in combined_text or "much longer" in combined_text


class TestResourceDeletionCascadesChunks:
    def test_deleting_resource_removes_its_chunks(self, client: TestClient, chunks_collection):
        resource = _create_resource(client, type="note", sourceUrl=None)
        client.post(f"/api/v1/resources/{resource['id']}/process")
        assert chunks_collection.count_documents({"resource_id": resource["id"]}) > 0

        delete_response = client.delete(f"/api/v1/resources/{resource['id']}")
        assert delete_response.status_code == 204

        assert chunks_collection.count_documents({"resource_id": resource["id"]}) == 0


class TestProcessingErrors:
    def test_process_missing_resource_returns_404(self, client: TestClient):
        response = client.post("/api/v1/resources/000000000000000000000000/process")
        assert response.status_code == 404

    def test_processing_status_for_missing_resource_returns_404(self, client: TestClient):
        response = client.get("/api/v1/resources/000000000000000000000000/processing-status")
        assert response.status_code == 404

    def test_process_malformed_id_returns_404(self, client: TestClient):
        response = client.post("/api/v1/resources/not-an-object-id/process")
        assert response.status_code == 404


class TestAlreadyProcessingGuard:
    def test_starting_processing_twice_while_in_flight_raises(self):
        """
        TestClient runs FastAPI BackgroundTasks synchronously, so there's no
        real window in which an HTTP round-trip observes PROCESSING -- this
        exercises the service-layer guard directly instead (with its own
        Mongo connection, bound to its own event loop, independent of the
        `client` fixture's) simulating the state a slow/large document would
        leave mid-flight in production.
        """

        async def _scenario() -> bool:
            mongodb.connect()
            try:
                resource = await resource_repository.create(
                    ResourceCreate(title="Guard test", type=ResourceType.NOTE, content="hello"),
                    _TEST_USER_ID,
                )
                await processing_service.start_processing(resource.id, _TEST_USER_ID)  # -> PROCESSING
                try:
                    await processing_service.start_processing(resource.id, _TEST_USER_ID)
                    return False
                except processing_service.AlreadyProcessingError:
                    return True
            finally:
                mongodb.close()

        assert asyncio.run(_scenario())

    def test_reprocessing_a_ready_resource_is_allowed(self, client: TestClient):
        resource = _create_resource(client, type="note", sourceUrl=None)
        client.post(f"/api/v1/resources/{resource['id']}/process")

        second_response = client.post(f"/api/v1/resources/{resource['id']}/process")
        assert second_response.status_code == 202


class TestAutomaticEmbeddingAfterProcessing:
    """processing_service.run_processing() auto-chains into
    embedding_service's own start_embedding/run_embedding once a resource
    reaches READY -- see app/config.py:auto_embed_after_processing (off by
    default for the whole suite via tests/conftest.py, so tests elsewhere
    that only care about chunking never incidentally call an embedding
    provider). Each test here turns it back on locally alongside a fake
    provider, so nothing ever reaches the real Gemini API."""

    def test_successful_processing_automatically_embeds_the_resource(
        self, client: TestClient, monkeypatch, chunks_collection
    ):
        monkeypatch.setattr(settings, "auto_embed_after_processing", True)
        fake = FakeEmbeddingProvider()
        monkeypatch.setattr(embedding_service, "get_embedding_provider", lambda: fake)

        resource = _create_resource(client, type="note", sourceUrl=None)
        response = client.post(f"/api/v1/resources/{resource['id']}/process")
        assert response.status_code == 202, response.text

        fetched = client.get(f"/api/v1/resources/{resource['id']}").json()
        assert fetched["status"] == "embedded"

        stored = list(chunks_collection.find({"resource_id": resource["id"]}))
        assert len(stored) > 0
        assert all(c["embedding"] is not None for c in stored)
        assert all(len(c["embedding"]) == fake.dimensions for c in stored)
        assert len(fake.calls) > 0

    def test_processing_failure_does_not_start_embedding(self, client: TestClient, monkeypatch):
        monkeypatch.setattr(settings, "auto_embed_after_processing", True)
        fake = FakeEmbeddingProvider()
        monkeypatch.setattr(embedding_service, "get_embedding_provider", lambda: fake)

        resource = _create_resource(client, type="note", sourceUrl=None, content=None)
        client.post(f"/api/v1/resources/{resource['id']}/process")

        fetched = client.get(f"/api/v1/resources/{resource['id']}").json()
        assert fetched["status"] == "failed"
        assert fake.calls == []  # embedding was never even attempted

    def test_automatic_embedding_failure_leaves_resource_retryable(
        self, client: TestClient, monkeypatch
    ):
        """An auto-embed that fails (e.g. Gemini quota/misconfiguration)
        leaves the resource FAILED with its chunks already in place -- not
        stuck, and not falsely reported as fully ready -- so the existing
        manual 'Embed' button can retry it."""
        monkeypatch.setattr(settings, "auto_embed_after_processing", True)
        monkeypatch.setattr(embedding_service.asyncio, "sleep", _instant_sleep)
        failing = FakeEmbeddingProvider(fail_times=10)
        monkeypatch.setattr(embedding_service, "get_embedding_provider", lambda: failing)

        resource = _create_resource(client, type="note", sourceUrl=None)
        client.post(f"/api/v1/resources/{resource['id']}/process")

        embed_status = client.get(f"/api/v1/resources/{resource['id']}/embedding-status").json()
        assert embed_status["status"] == "failed"
        assert embed_status["embeddedChunkCount"] == 0
        assert embed_status["totalChunkCount"] > 0  # chunking itself succeeded
        assert embed_status["processingError"]

        # Retryable via the existing manual endpoint, once the provider works.
        working = FakeEmbeddingProvider()
        monkeypatch.setattr(embedding_service, "get_embedding_provider", lambda: working)
        retry_response = client.post(f"/api/v1/resources/{resource['id']}/embed")
        assert retry_response.status_code == 202

        retried_status = client.get(f"/api/v1/resources/{resource['id']}/embedding-status").json()
        assert retried_status["status"] == "embedded"
        assert retried_status["embeddedChunkCount"] == retried_status["totalChunkCount"]

    def test_retrying_embedding_after_auto_embed_does_not_duplicate_chunks_or_embeddings(
        self, client: TestClient, monkeypatch, chunks_collection
    ):
        monkeypatch.setattr(settings, "auto_embed_after_processing", True)
        fake = FakeEmbeddingProvider()
        monkeypatch.setattr(embedding_service, "get_embedding_provider", lambda: fake)

        resource = _create_resource(client, type="note", sourceUrl=None)
        client.post(f"/api/v1/resources/{resource['id']}/process")  # chunks, then auto-embeds

        chunk_count_after_auto_embed = chunks_collection.count_documents(
            {"resource_id": resource["id"]}
        )
        calls_after_auto_embed = len(fake.calls)
        assert chunk_count_after_auto_embed > 0
        assert calls_after_auto_embed > 0

        # A manual re-embed afterwards must not create duplicate chunk
        # documents, nor call the provider again for chunks that already
        # have a vector from the automatic run.
        client.post(f"/api/v1/resources/{resource['id']}/embed")

        assert (
            chunks_collection.count_documents({"resource_id": resource["id"]})
            == chunk_count_after_auto_embed
        )
        assert len(fake.calls) == calls_after_auto_embed

    def test_concurrent_embed_requests_for_the_same_resource_do_not_both_succeed(self):
        """Two overlapping start_embedding calls for the same resource --
        e.g. the automatic post-processing embed racing a manual double
        click of "Embed" -- must not both flip the resource into EMBEDDING.
        Exactly one should win the atomic compare-and-swap
        (resource_repository.set_processing_state's `expected_statuses`);
        the other must observe AlreadyEmbeddingError rather than also
        starting a second, overlapping embedding run."""

        async def _scenario() -> tuple[int, int]:
            mongodb.connect()
            try:
                resource = await resource_repository.create(
                    ResourceCreate(
                        title="Concurrent embed race test",
                        type=ResourceType.NOTE,
                        content="hello world " * 20,
                    ),
                    _TEST_USER_ID,
                )
                await processing_service.run_processing(resource.id, _TEST_USER_ID)  # -> READY

                results = await asyncio.gather(
                    embedding_service.start_embedding(resource.id, _TEST_USER_ID),
                    embedding_service.start_embedding(resource.id, _TEST_USER_ID),
                    return_exceptions=True,
                )
                successes = sum(1 for r in results if not isinstance(r, Exception))
                already_embedding = sum(
                    1 for r in results if isinstance(r, embedding_service.AlreadyEmbeddingError)
                )
                return successes, already_embedding
            finally:
                mongodb.close()

        successes, already_embedding = asyncio.run(_scenario())
        assert successes == 1
        assert already_embedding == 1
