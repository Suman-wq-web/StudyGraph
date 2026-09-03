"""
Tests for GET /api/v1/graph (app/api/v1/graph.py, app/services/graph_service.py).
Real local Mongo, no Atlas features needed -- concepts/edges are plain
document reads/writes. Seeds data via POST /{id}/extract (with a
FakeGenerationProvider, mirroring test_graph_extraction_pipeline.py) rather
than writing to the repositories directly, so the whole extract -> read path
is exercised through the same TestClient/event loop.
"""

from fastapi.testclient import TestClient

from app.services import graph_extraction_service
from app.services.rag.generation import GenerationChunk, GenerationProvider


class FakeGenerationProvider(GenerationProvider):
    def __init__(self, responses=None):
        self._responses = list(responses or [])

    @property
    def model_name(self) -> str:
        return "fake-generation-model"

    async def stream_generate(self, *, system_prompt: str, user_prompt: str):
        text = self._responses.pop(0) if self._responses else '{"concepts": [], "relationships": []}'
        yield GenerationChunk(text=text, finish_reason="STOP")


def _create_and_process_note(client: TestClient) -> dict:
    payload = {
        "title": "Graph API test",
        "type": "note",
        "content": "Calculus is needed before gradient descent. " * 20,
    }
    response = client.post("/api/v1/resources", json=payload)
    resource = response.json()
    client.post(f"/api/v1/resources/{resource['id']}/process")
    return client.get(f"/api/v1/resources/{resource['id']}").json()


class TestEmptyGraph:
    def test_no_concepts_returns_empty_graph(self, client: TestClient):
        response = client.get("/api/v1/graph")
        assert response.status_code == 200
        assert response.json() == {"nodes": [], "edges": []}


class TestPopulatedGraph:
    def test_returns_nodes_and_edges_with_centrality(self, client: TestClient, monkeypatch):
        response_text = (
            '{"concepts": [{"name": "Calculus"}, {"name": "Gradient Descent"}], '
            '"relationships": [{"source": "Calculus", "relation_type": "prerequisite_of", '
            '"target": "Gradient Descent"}]}'
        )
        resource = _create_and_process_note(client)
        fake = FakeGenerationProvider(responses=[response_text] * 10)
        monkeypatch.setattr(graph_extraction_service, "get_generation_provider", lambda: fake)
        client.post(f"/api/v1/resources/{resource['id']}/extract")

        response = client.get("/api/v1/graph")
        body = response.json()

        assert {n["name"] for n in body["nodes"]} == {"Calculus", "Gradient Descent"}
        assert len(body["edges"]) == 1
        assert body["edges"][0]["relationType"] == "prerequisite_of"
        for node in body["nodes"]:
            assert node["centralityScore"] is not None

    def test_centrality_is_written_back_to_stored_concepts(
        self, client: TestClient, monkeypatch, concepts_collection
    ):
        response_text = '{"concepts": [{"name": "Solo Concept"}], "relationships": []}'
        resource = _create_and_process_note(client)
        fake = FakeGenerationProvider(responses=[response_text] * 10)
        monkeypatch.setattr(graph_extraction_service, "get_generation_provider", lambda: fake)
        client.post(f"/api/v1/resources/{resource['id']}/extract")

        client.get("/api/v1/graph")

        stored = concepts_collection.find_one({"name": "Solo Concept"})
        assert stored["centrality_score"] is not None
