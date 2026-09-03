"""
Tests for POST /api/v1/chat (app/api/v1/chat.py). No real Gemini/Atlas calls
-- app/services/rag/pipeline.py:retrieve_context and
app/services/rag/generation.py:get_generation_provider are both
mocked/injected at the route boundary, mirroring test_search.py's approach.
"""

import json

from fastapi.testclient import TestClient

from app.services.rag import generation, pipeline, retrieval
from app.services.rag.generation import GenerationChunk, GenerationProvider, GenerationProviderError


class FakeGenerationProvider(GenerationProvider):
    def __init__(self, chunks: list[GenerationChunk], *, fail_after_chunk_index: int | None = None):
        self._chunks = chunks
        self._fail_after_chunk_index = fail_after_chunk_index

    @property
    def model_name(self) -> str:
        return "fake-generation-model"

    async def stream_generate(self, *, system_prompt: str, user_prompt: str):
        for index, chunk in enumerate(self._chunks):
            if self._fail_after_chunk_index is not None and index == self._fail_after_chunk_index:
                raise GenerationProviderError("failed mid-stream")
            yield chunk


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    """Splits raw SSE text into (event, parsed-json-data) pairs."""
    frames = [f for f in body.split("\n\n") if f.strip()]
    parsed = []
    for frame in frames:
        event = None
        data = None
        for line in frame.splitlines():
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:") :].strip())
        parsed.append((event, data))
    return parsed


class TestRequestValidation:
    def test_empty_query_is_rejected(self, client: TestClient):
        response = client.post("/api/v1/chat", json={"query": ""})
        assert response.status_code == 422

    def test_missing_query_is_rejected(self, client: TestClient):
        response = client.post("/api/v1/chat", json={})
        assert response.status_code == 422

    def test_top_k_below_minimum_is_rejected(self, client: TestClient):
        response = client.post("/api/v1/chat", json={"query": "x", "topK": 0})
        assert response.status_code == 422

    def test_top_k_above_maximum_is_rejected(self, client: TestClient):
        response = client.post("/api/v1/chat", json={"query": "x", "topK": 21})
        assert response.status_code == 422

    def test_invalid_resource_type_is_rejected(self, client: TestClient):
        response = client.post("/api/v1/chat", json={"query": "x", "resourceType": "podcast"})
        assert response.status_code == 422


class TestUnavailabilityHandling:
    def test_misconfigured_generation_provider_returns_503(self, client: TestClient, monkeypatch):
        def failing_get_provider():
            raise GenerationProviderError("GEMINI_API_KEY is not configured.")

        monkeypatch.setattr(generation, "get_generation_provider", failing_get_provider)

        response = client.post("/api/v1/chat", json={"query": "hello"})

        assert response.status_code == 503
        assert "detail" in response.json()

    def test_embedding_unavailable_returns_503(self, client: TestClient, monkeypatch):
        monkeypatch.setattr(
            generation, "get_generation_provider", lambda: FakeGenerationProvider([])
        )

        async def raiser(*args, **kwargs):
            raise retrieval.EmbeddingUnavailableError("Gemini rejected the request")

        monkeypatch.setattr(pipeline, "retrieve_context", raiser)

        response = client.post("/api/v1/chat", json={"query": "hello"})

        assert response.status_code == 503

    def test_retrieval_unavailable_returns_503(self, client: TestClient, monkeypatch):
        monkeypatch.setattr(
            generation, "get_generation_provider", lambda: FakeGenerationProvider([])
        )

        async def raiser(*args, **kwargs):
            raise retrieval.RetrievalUnavailableError("both retrievers failed")

        monkeypatch.setattr(pipeline, "retrieve_context", raiser)

        response = client.post("/api/v1/chat", json={"query": "hello"})

        assert response.status_code == 503


class TestStreamingHappyPath:
    def test_citations_then_tokens_then_done(self, client: TestClient, monkeypatch):
        async def fake_retrieve_context(*args, **kwargs):
            return pipeline.RagContext(query="hello", chunks=[], citations=[])

        monkeypatch.setattr(pipeline, "retrieve_context", fake_retrieve_context)
        monkeypatch.setattr(
            generation,
            "get_generation_provider",
            lambda: FakeGenerationProvider(
                [GenerationChunk(text="Hi "), GenerationChunk(text="there!", finish_reason="STOP")]
            ),
        )

        with client.stream("POST", "/api/v1/chat", json={"query": "hello"}) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = "".join(response.iter_text())

        frames = _parse_sse(body)
        events = [event for event, _ in frames]
        assert events == ["citations", "token", "token", "done"]
        assert frames[0][1]["citations"] == []
        assert frames[1][1]["delta"] == "Hi "
        assert frames[2][1]["delta"] == "there!"
        assert frames[3][1]["finishReason"] == "STOP"

    def test_mid_stream_failure_is_a_200_with_terminal_error_frame(self, client: TestClient, monkeypatch):
        async def fake_retrieve_context(*args, **kwargs):
            return pipeline.RagContext(query="hello", chunks=[], citations=[])

        monkeypatch.setattr(pipeline, "retrieve_context", fake_retrieve_context)
        monkeypatch.setattr(
            generation,
            "get_generation_provider",
            lambda: FakeGenerationProvider(
                [GenerationChunk(text="partial"), GenerationChunk(text="more")],
                fail_after_chunk_index=1,
            ),
        )

        with client.stream("POST", "/api/v1/chat", json={"query": "hello"}) as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

        frames = _parse_sse(body)
        events = [event for event, _ in frames]
        assert events == ["citations", "token", "error"]
        assert "message" in frames[-1][1]
