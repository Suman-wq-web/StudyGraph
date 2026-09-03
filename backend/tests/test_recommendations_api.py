"""
Tests for GET /api/v1/recommendations (app/api/v1/recommendations.py,
app/services/recommendation_service.py). Real local Mongo, no Atlas
features needed. Seeds data via POST /{id}/extract (with a
FakeGenerationProvider) the same way test_graph_api.py does, so the whole
extract -> read path is exercised through the same TestClient/event loop.
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


def _create_and_process_note(client: TestClient, content: str) -> dict:
    payload = {"title": "Recommendations API test", "type": "note", "content": content}
    response = client.post("/api/v1/resources", json=payload)
    resource = response.json()
    client.post(f"/api/v1/resources/{resource['id']}/process")
    return client.get(f"/api/v1/resources/{resource['id']}").json()


def _extract(client: TestClient, monkeypatch, resource_id: str, response_text: str) -> None:
    fake = FakeGenerationProvider(responses=[response_text] * 10)
    monkeypatch.setattr(graph_extraction_service, "get_generation_provider", lambda: fake)
    client.post(f"/api/v1/resources/{resource_id}/extract")


class TestEmptyGraph:
    def test_no_concepts_returns_empty_items(self, client: TestClient):
        response = client.get("/api/v1/recommendations")

        assert response.status_code == 200
        assert response.json() == {"items": []}


class TestPopulatedGraph:
    def test_returns_gap_and_next_step_recommendations(self, client: TestClient, monkeypatch):
        # "Photosynthesis" is a prerequisite for two other concepts but only
        # ever mentioned in this one resource -- a gap. "Basics" is a
        # prerequisite for "Photosynthesis" and gets extracted from two
        # separate resources -- well covered, so "Photosynthesis" (shallower)
        # should also surface as a next step from it.
        resource_a = _create_and_process_note(
            client,
            "Basics is needed before Photosynthesis. " * 20,
        )
        response_a = (
            '{"concepts": [{"name": "Basics"}, {"name": "Photosynthesis"}], '
            '"relationships": [{"source": "Basics", "relation_type": "prerequisite_of", '
            '"target": "Photosynthesis"}]}'
        )
        _extract(client, monkeypatch, resource_a["id"], response_a)

        resource_b = _create_and_process_note(
            client,
            "Photosynthesis is needed before Cellular Respiration. "
            "Photosynthesis is needed before Carbon Cycle. "
            "Basics is a foundational topic. " * 20,
        )
        response_b = (
            '{"concepts": [{"name": "Basics"}, {"name": "Photosynthesis"}, '
            '{"name": "Cellular Respiration"}, {"name": "Carbon Cycle"}], '
            '"relationships": ['
            '{"source": "Photosynthesis", "relation_type": "prerequisite_of", '
            '"target": "Cellular Respiration"}, '
            '{"source": "Photosynthesis", "relation_type": "prerequisite_of", '
            '"target": "Carbon Cycle"}]}'
        )
        _extract(client, monkeypatch, resource_b["id"], response_b)

        response = client.get("/api/v1/recommendations")
        body = response.json()

        assert response.status_code == 200
        assert body["items"], "expected at least one recommendation"

        reason_types = {item["reasonType"] for item in body["items"]}
        concept_names = {item["conceptName"] for item in body["items"]}
        assert "gap" in reason_types
        assert "Photosynthesis" in concept_names

        for item in body["items"]:
            assert set(item.keys()) == {
                "conceptId",
                "conceptName",
                "reasonType",
                "reason",
                "score",
                "relatedConceptIds",
                "sourceResourceIds",
            }
            assert isinstance(item["reason"], str) and item["reason"]

    def test_limit_query_param_caps_item_count(self, client: TestClient, monkeypatch):
        resource = _create_and_process_note(
            client,
            "Basics is needed before A. Basics is needed before B. "
            "Basics is needed before C. Basics is needed before D. " * 10,
        )
        response_text = (
            '{"concepts": [{"name": "Basics"}, {"name": "A"}, {"name": "B"}, '
            '{"name": "C"}, {"name": "D"}], '
            '"relationships": ['
            '{"source": "Basics", "relation_type": "prerequisite_of", "target": "A"}, '
            '{"source": "Basics", "relation_type": "prerequisite_of", "target": "B"}, '
            '{"source": "Basics", "relation_type": "prerequisite_of", "target": "C"}, '
            '{"source": "Basics", "relation_type": "prerequisite_of", "target": "D"}]}'
        )
        _extract(client, monkeypatch, resource["id"], response_text)

        response = client.get("/api/v1/recommendations", params={"limit": 1})

        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_invalid_limit_is_rejected(self, client: TestClient):
        response = client.get("/api/v1/recommendations", params={"limit": 0})

        assert response.status_code == 422
