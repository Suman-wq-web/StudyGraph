from fastapi.testclient import TestClient


def _create(client: TestClient, **overrides) -> dict:
    payload = {
        "title": "Attention Is All You Need",
        "type": "article",
        "sourceUrl": "https://arxiv.org/abs/1706.03762",
        "tags": ["nlp", "transformers"],
        **overrides,
    }
    response = client.post("/api/v1/resources", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


class TestCreateResource:
    def test_create_article(self, client: TestClient):
        body = _create(client)
        assert body["title"] == "Attention Is All You Need"
        assert body["type"] == "article"
        assert body["status"] == "pending"
        assert body["tags"] == ["nlp", "transformers"]
        assert body["id"]
        assert body["createdAt"] == body["updatedAt"]

    def test_create_video(self, client: TestClient):
        body = _create(client, type="video", title="3Blue1Brown: Neural Networks",
                        sourceUrl="https://www.youtube.com/watch?v=aircAruvnKk")
        assert body["type"] == "video"

    def test_create_url(self, client: TestClient):
        body = _create(client, type="url", title="Some bookmark", sourceUrl="https://example.com")
        assert body["type"] == "url"

    def test_create_note(self, client: TestClient):
        body = _create(client, type="note", title="My notes", sourceUrl=None,
                        content="Free-form thoughts on gradient descent.")
        assert body["type"] == "note"
        assert body["sourceUrl"] is None
        assert body["content"] == "Free-form thoughts on gradient descent."

    def test_tags_are_lowercased_and_deduplicated(self, client: TestClient):
        body = _create(client, tags=["NLP", "nlp", " Transformers "])
        assert body["tags"] == ["nlp", "transformers"]


class TestValidationErrors:
    def test_missing_title(self, client: TestClient):
        response = client.post("/api/v1/resources", json={"type": "article"})
        assert response.status_code == 422

    def test_blank_title(self, client: TestClient):
        response = client.post("/api/v1/resources", json={"title": "   ", "type": "note"})
        assert response.status_code == 422

    def test_invalid_type(self, client: TestClient):
        response = client.post("/api/v1/resources", json={"title": "X", "type": "podcast"})
        assert response.status_code == 422

    def test_invalid_source_url_scheme(self, client: TestClient):
        response = client.post(
            "/api/v1/resources",
            json={"title": "X", "type": "url", "sourceUrl": "ftp://example.com"},
        )
        assert response.status_code == 422

    def test_too_many_tags_rejected(self, client: TestClient):
        response = client.post(
            "/api/v1/resources",
            json={"title": "X", "type": "note", "tags": [f"tag{i}" for i in range(21)]},
        )
        assert response.status_code == 422

    def test_title_too_long_rejected(self, client: TestClient):
        response = client.post(
            "/api/v1/resources",
            json={"title": "x" * 201, "type": "note"},
        )
        assert response.status_code == 422


class TestListResources:
    def test_list_empty(self, client: TestClient):
        response = client.get("/api/v1/resources")
        assert response.status_code == 200
        body = response.json()
        assert body == {"items": [], "total": 0, "skip": 0, "limit": 20}

    def test_list_returns_created_resources_newest_first(self, client: TestClient):
        first = _create(client, title="First")
        second = _create(client, title="Second")

        response = client.get("/api/v1/resources")
        body = response.json()
        assert body["total"] == 2
        ids = [item["id"] for item in body["items"]]
        assert ids == [second["id"], first["id"]]

    def test_filter_by_type(self, client: TestClient):
        _create(client, type="article", title="An article")
        _create(client, type="note", title="A note", sourceUrl=None)

        response = client.get("/api/v1/resources", params={"type": "note"})
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["type"] == "note"

    def test_filter_by_tag(self, client: TestClient):
        _create(client, title="Tagged", tags=["ml"])
        _create(client, title="Untagged", tags=[])

        response = client.get("/api/v1/resources", params={"tag": "ml"})
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Tagged"

    def test_search_matches_title(self, client: TestClient):
        _create(client, title="Deep Learning Basics")
        _create(client, title="Something else entirely")

        response = client.get("/api/v1/resources", params={"search": "deep learning"})
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Deep Learning Basics"

    def test_pagination(self, client: TestClient):
        for i in range(3):
            _create(client, title=f"Resource {i}")

        response = client.get("/api/v1/resources", params={"skip": 1, "limit": 1})
        body = response.json()
        assert body["total"] == 3
        assert body["skip"] == 1
        assert body["limit"] == 1
        assert len(body["items"]) == 1


class TestGetResource:
    def test_get_existing(self, client: TestClient):
        created = _create(client)
        response = client.get(f"/api/v1/resources/{created['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    def test_get_missing_returns_404(self, client: TestClient):
        response = client.get("/api/v1/resources/000000000000000000000000")
        assert response.status_code == 404

    def test_get_malformed_id_returns_404(self, client: TestClient):
        response = client.get("/api/v1/resources/not-a-valid-object-id")
        assert response.status_code == 404


class TestUpdateResource:
    def test_partial_update_title(self, client: TestClient):
        created = _create(client)
        response = client.patch(f"/api/v1/resources/{created['id']}", json={"title": "New title"})
        assert response.status_code == 200
        body = response.json()
        assert body["title"] == "New title"
        assert body["type"] == created["type"]
        assert body["updatedAt"] >= created["updatedAt"]

    def test_update_tags(self, client: TestClient):
        created = _create(client, tags=["a"])
        response = client.patch(f"/api/v1/resources/{created['id']}", json={"tags": ["b", "c"]})
        assert response.status_code == 200
        assert response.json()["tags"] == ["b", "c"]

    def test_update_missing_returns_404(self, client: TestClient):
        response = client.patch(
            "/api/v1/resources/000000000000000000000000", json={"title": "X"}
        )
        assert response.status_code == 404

    def test_update_rejects_blank_title(self, client: TestClient):
        created = _create(client)
        response = client.patch(f"/api/v1/resources/{created['id']}", json={"title": "   "})
        assert response.status_code == 422

    def test_update_rejects_invalid_source_url(self, client: TestClient):
        created = _create(client)
        response = client.patch(
            f"/api/v1/resources/{created['id']}", json={"sourceUrl": "not-a-url"}
        )
        assert response.status_code == 422


class TestDeleteResource:
    def test_delete_existing(self, client: TestClient):
        created = _create(client)
        response = client.delete(f"/api/v1/resources/{created['id']}")
        assert response.status_code == 204

        follow_up = client.get(f"/api/v1/resources/{created['id']}")
        assert follow_up.status_code == 404

    def test_delete_missing_returns_404(self, client: TestClient):
        response = client.delete("/api/v1/resources/000000000000000000000000")
        assert response.status_code == 404


class TestResourceStats:
    def test_stats_reflect_created_resources(self, client: TestClient):
        _create(client, type="article")
        _create(client, type="note", sourceUrl=None)
        _create(client, type="note", sourceUrl=None)

        response = client.get("/api/v1/resources/stats")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert body["byType"]["article"] == 1
        assert body["byType"]["note"] == 2
        assert body["byStatus"]["pending"] == 3
