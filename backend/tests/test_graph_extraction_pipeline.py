"""
Tests for the extraction pipeline (app/services/graph_extraction_service.py)
and its API endpoints. No real Gemini calls -- a FakeGenerationProvider test
double stands in wherever a provider is needed, mirroring
test_embedding_pipeline.py's FakeEmbeddingProvider.
"""

from fastapi.testclient import TestClient

from app.services import graph_extraction_service
from app.services.rag.generation import GenerationChunk, GenerationProvider, GenerationRateLimitError


class FakeGenerationProvider(GenerationProvider):
    def __init__(self, responses=None, *, fail_times: int = 0, error_cls=GenerationRateLimitError):
        self.calls: list[tuple[str, str]] = []
        self._responses = list(responses or [])
        self._fail_times = fail_times
        self._error_cls = error_cls

    @property
    def model_name(self) -> str:
        return "fake-generation-model"

    async def stream_generate(self, *, system_prompt: str, user_prompt: str):
        self.calls.append((system_prompt, user_prompt))
        if self._fail_times > 0:
            self._fail_times -= 1
            raise self._error_cls("simulated failure")
        text = self._responses.pop(0) if self._responses else '{"concepts": [], "relationships": []}'
        yield GenerationChunk(text=text, finish_reason="STOP")


ONE_CONCEPT_RESPONSE = '{"concepts": [{"name": "Gradient Descent", "description": "d"}], "relationships": []}'


def _create_and_process_note(client: TestClient, content: str | None = None) -> dict:
    payload = {
        "title": "Extraction pipeline test",
        "type": "note",
        "content": content or ("Gradient descent is an optimization algorithm. " * 20),
    }
    response = client.post("/api/v1/resources", json=payload)
    assert response.status_code == 201, response.text
    resource = response.json()
    process_response = client.post(f"/api/v1/resources/{resource['id']}/process")
    assert process_response.status_code == 202, process_response.text
    return client.get(f"/api/v1/resources/{resource['id']}").json()


class TestExtractEndpointHappyPath:
    def test_extracting_a_chunked_resource_writes_concepts(
        self, client: TestClient, monkeypatch, concepts_collection
    ):
        resource = _create_and_process_note(client)
        fake = FakeGenerationProvider(responses=[ONE_CONCEPT_RESPONSE] * 10)
        monkeypatch.setattr(graph_extraction_service, "get_generation_provider", lambda: fake)

        response = client.post(f"/api/v1/resources/{resource['id']}/extract")
        assert response.status_code == 202
        assert response.json()["chunksPending"] > 0

        status_response = client.get(f"/api/v1/resources/{resource['id']}/extraction-status")
        body = status_response.json()
        assert body["extractedChunkCount"] == body["totalChunkCount"]
        assert body["totalChunkCount"] > 0

        stored = list(concepts_collection.find({}))
        assert len(stored) == 1
        assert stored[0]["name"] == "Gradient Descent"

    def test_extracting_without_chunks_returns_409(self, client: TestClient):
        create_response = client.post(
            "/api/v1/resources", json={"title": "Not processed", "type": "note", "content": "hi"}
        )
        resource = create_response.json()

        response = client.post(f"/api/v1/resources/{resource['id']}/extract")
        assert response.status_code == 409

    def test_extract_missing_resource_returns_404(self, client: TestClient):
        response = client.post("/api/v1/resources/000000000000000000000000/extract")
        assert response.status_code == 404

    def test_extraction_status_missing_resource_returns_404(self, client: TestClient):
        response = client.get("/api/v1/resources/000000000000000000000000/extraction-status")
        assert response.status_code == 404


class TestDedupeAcrossChunks:
    def test_the_same_concept_mentioned_in_two_chunks_becomes_one_node(
        self, client: TestClient, monkeypatch, concepts_collection
    ):
        # Long enough to guarantee multiple chunks (default 512-token window).
        resource = _create_and_process_note(client, content="Gradient descent details. " * 400)
        fake = FakeGenerationProvider(responses=[ONE_CONCEPT_RESPONSE] * 20)
        monkeypatch.setattr(graph_extraction_service, "get_generation_provider", lambda: fake)

        client.post(f"/api/v1/resources/{resource['id']}/extract")

        status_body = client.get(f"/api/v1/resources/{resource['id']}/extraction-status").json()
        assert status_body["totalChunkCount"] > 1
        assert len(fake.calls) == status_body["totalChunkCount"]

        stored = list(concepts_collection.find({}))
        assert len(stored) == 1
        assert stored[0]["source_resource_ids"] == [resource["id"]]


class TestIdempotentReextraction:
    def test_reextraction_skips_already_extracted_chunks(self, client: TestClient, monkeypatch):
        resource = _create_and_process_note(client)
        fake = FakeGenerationProvider(responses=[ONE_CONCEPT_RESPONSE] * 10)
        monkeypatch.setattr(graph_extraction_service, "get_generation_provider", lambda: fake)

        client.post(f"/api/v1/resources/{resource['id']}/extract")
        calls_after_first_run = len(fake.calls)
        assert calls_after_first_run > 0

        client.post(f"/api/v1/resources/{resource['id']}/extract")

        assert len(fake.calls) == calls_after_first_run


class TestPartialFailureHandling:
    def test_unparseable_chunk_is_skipped_and_left_unextracted(self, client: TestClient, monkeypatch):
        resource = _create_and_process_note(client)
        fake = FakeGenerationProvider(responses=["not json", "still not json"])
        monkeypatch.setattr(graph_extraction_service, "get_generation_provider", lambda: fake)

        client.post(f"/api/v1/resources/{resource['id']}/extract")

        status_body = client.get(f"/api/v1/resources/{resource['id']}/extraction-status").json()
        assert status_body["extractedChunkCount"] == 0

    def test_provider_unavailable_leaves_extraction_status_at_zero(self, client: TestClient, monkeypatch):
        monkeypatch.setattr("app.config.settings.gemini_api_key", "")
        resource = _create_and_process_note(client)

        client.post(f"/api/v1/resources/{resource['id']}/extract")

        status_body = client.get(f"/api/v1/resources/{resource['id']}/extraction-status").json()
        assert status_body["extractedChunkCount"] == 0


class TestRelationshipExtraction:
    def test_relationship_between_two_concepts_creates_an_edge(
        self, client: TestClient, monkeypatch, edges_collection
    ):
        response_text = (
            '{"concepts": [{"name": "Calculus"}, {"name": "Gradient Descent"}], '
            '"relationships": [{"source": "Calculus", "relation_type": "prerequisite_of", '
            '"target": "Gradient Descent"}]}'
        )
        resource = _create_and_process_note(client)
        fake = FakeGenerationProvider(responses=[response_text] * 10)
        monkeypatch.setattr(graph_extraction_service, "get_generation_provider", lambda: fake)

        client.post(f"/api/v1/resources/{resource['id']}/extract")

        stored_edges = list(edges_collection.find({}))
        assert len(stored_edges) == 1
        assert stored_edges[0]["relation_type"] == "prerequisite_of"
        assert stored_edges[0]["evidence_chunk_ids"]
