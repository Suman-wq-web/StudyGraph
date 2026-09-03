"""API tests for reading/watch progress (app/api/v1/resources.py's
/progress routes, app/services/progress_service.py). Mirrors
test_resources.py's style: the `client` fixture is one authenticated user
(TEST_USER_EMAIL); a second user is registered inline wherever a test needs
to prove isolation, same pattern test_auth.py's repeat-login test uses
(per-request `headers=` override rather than a second TestClient)."""

from fastapi.testclient import TestClient


def _create_resource(client: TestClient, **overrides) -> dict:
    payload = {
        "title": "Deep Learning Specialization",
        "type": "video",
        "sourceUrl": "https://www.youtube.com/watch?v=aircAruvnKk",
        **overrides,
    }
    response = client.post("/api/v1/resources", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _second_user_headers(client: TestClient) -> dict:
    """Registers and logs in an independent second user, returning headers
    that authenticate as them (overriding the `client` fixture's default
    Authorization header for just that one request)."""
    client.post(
        "/api/v1/auth/register",
        json={"email": "progress-other-user@example.com", "password": "other-password-123"},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "progress-other-user@example.com", "password": "other-password-123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['accessToken']}"}


class TestGetProgress:
    def test_before_any_activity_returns_not_started_default(self, client: TestClient):
        resource = _create_resource(client)
        response = client.get(f"/api/v1/resources/{resource['id']}/progress")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "not_started"
        assert body["progressPercent"] == 0
        assert body["resourceId"] == resource["id"]
        assert body["id"] is None

    def test_for_nonexistent_resource_returns_404(self, client: TestClient):
        response = client.get("/api/v1/resources/656565656565656565656567/progress")
        assert response.status_code == 404

    def test_for_another_users_resource_returns_404(self, client: TestClient):
        other_headers = _second_user_headers(client)
        other_resource = client.post(
            "/api/v1/resources",
            json={"title": "Not yours", "type": "note", "content": "secret"},
            headers=other_headers,
        ).json()

        response = client.get(f"/api/v1/resources/{other_resource['id']}/progress")
        assert response.status_code == 404


class TestUpdateProgress:
    def test_progress_percent_sets_in_progress(self, client: TestClient):
        resource = _create_resource(client, type="note", sourceUrl=None, content="Some notes.")
        response = client.patch(
            f"/api/v1/resources/{resource['id']}/progress", json={"progressPercent": 40}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "in_progress"
        assert body["progressPercent"] == 40

    def test_progress_percent_reaching_threshold_auto_completes(self, client: TestClient):
        resource = _create_resource(client, type="note", sourceUrl=None, content="Some notes.")
        response = client.patch(
            f"/api/v1/resources/{resource['id']}/progress", json={"progressPercent": 97}
        )
        body = response.json()
        assert body["status"] == "completed"
        assert body["progressPercent"] == 100

    def test_position_and_duration_computes_percent(self, client: TestClient):
        resource = _create_resource(client)
        response = client.patch(
            f"/api/v1/resources/{resource['id']}/progress",
            json={"positionSeconds": 30, "durationSeconds": 120},
        )
        body = response.json()
        assert body["status"] == "in_progress"
        assert body["progressPercent"] == 25.0
        assert body["positionSeconds"] == 30
        assert body["durationSeconds"] == 120

    def test_position_reaching_threshold_of_duration_auto_completes(self, client: TestClient):
        resource = _create_resource(client)
        response = client.patch(
            f"/api/v1/resources/{resource['id']}/progress",
            json={"positionSeconds": 118, "durationSeconds": 120},
        )
        body = response.json()
        assert body["status"] == "completed"
        assert body["progressPercent"] == 100

    def test_position_only_without_duration_is_in_progress_with_no_percent_claim(
        self, client: TestClient
    ):
        resource = _create_resource(client)
        response = client.patch(
            f"/api/v1/resources/{resource['id']}/progress", json={"positionSeconds": 15}
        )
        body = response.json()
        assert body["status"] == "in_progress"
        assert body["progressPercent"] == 0
        assert body["positionSeconds"] == 15

    def test_explicit_status_completed_forces_percent_to_100(self, client: TestClient):
        resource = _create_resource(client)
        response = client.patch(
            f"/api/v1/resources/{resource['id']}/progress", json={"status": "completed"}
        )
        body = response.json()
        assert body["status"] == "completed"
        assert body["progressPercent"] == 100

    def test_explicit_status_not_started_resets_percent(self, client: TestClient):
        resource = _create_resource(client)
        client.patch(f"/api/v1/resources/{resource['id']}/progress", json={"progressPercent": 50})
        response = client.patch(
            f"/api/v1/resources/{resource['id']}/progress", json={"status": "not_started"}
        )
        body = response.json()
        assert body["status"] == "not_started"
        assert body["progressPercent"] == 0

    def test_repeated_updates_upsert_rather_than_duplicate(
        self, client: TestClient, progress_collection
    ):
        resource = _create_resource(client)
        for percent in (10, 20, 30):
            client.patch(
                f"/api/v1/resources/{resource['id']}/progress", json={"progressPercent": percent}
            )
        assert progress_collection.count_documents({"resource_id": resource["id"]}) == 1

    def test_for_nonexistent_resource_returns_404(self, client: TestClient):
        response = client.patch(
            "/api/v1/resources/656565656565656565656567/progress", json={"progressPercent": 10}
        )
        assert response.status_code == 404

    def test_empty_payload_returns_current_progress_without_error(self, client: TestClient):
        resource = _create_resource(client)
        client.patch(f"/api/v1/resources/{resource['id']}/progress", json={"progressPercent": 20})
        response = client.patch(f"/api/v1/resources/{resource['id']}/progress", json={})
        assert response.status_code == 200
        assert response.json()["progressPercent"] == 20

    def test_out_of_range_percent_is_rejected(self, client: TestClient):
        resource = _create_resource(client)
        response = client.patch(
            f"/api/v1/resources/{resource['id']}/progress", json={"progressPercent": 150}
        )
        assert response.status_code == 422


class TestMarkCompleted:
    def test_sets_status_and_full_percent(self, client: TestClient):
        resource = _create_resource(client)
        client.patch(f"/api/v1/resources/{resource['id']}/progress", json={"progressPercent": 30})
        response = client.post(f"/api/v1/resources/{resource['id']}/progress/complete")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "completed"
        assert body["progressPercent"] == 100

    def test_without_prior_progress_still_works(self, client: TestClient):
        resource = _create_resource(client)
        response = client.post(f"/api/v1/resources/{resource['id']}/progress/complete")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    def test_for_nonexistent_resource_returns_404(self, client: TestClient):
        response = client.post("/api/v1/resources/656565656565656565656567/progress/complete")
        assert response.status_code == 404


class TestListInProgress:
    def test_empty_when_nothing_in_progress(self, client: TestClient):
        response = client.get("/api/v1/resources/progress/in-progress")
        assert response.status_code == 200
        assert response.json() == {"items": []}

    def test_excludes_not_started_and_completed(self, client: TestClient):
        untouched = _create_resource(client, title="Untouched")
        in_progress = _create_resource(client, title="Halfway")
        completed = _create_resource(client, title="Done")
        client.patch(f"/api/v1/resources/{in_progress['id']}/progress", json={"progressPercent": 40})
        client.post(f"/api/v1/resources/{completed['id']}/progress/complete")

        response = client.get("/api/v1/resources/progress/in-progress")
        titles = [item["title"] for item in response.json()["items"]]
        assert titles == ["Halfway"]
        assert untouched["id"] not in [i["resourceId"] for i in response.json()["items"]]

    def test_returns_newest_activity_first(self, client: TestClient):
        first = _create_resource(client, title="First")
        second = _create_resource(client, title="Second")
        client.patch(f"/api/v1/resources/{first['id']}/progress", json={"progressPercent": 10})
        client.patch(f"/api/v1/resources/{second['id']}/progress", json={"progressPercent": 10})
        # Touch `first` again so it's the most recently updated.
        client.patch(f"/api/v1/resources/{first['id']}/progress", json={"progressPercent": 20})

        response = client.get("/api/v1/resources/progress/in-progress")
        ids = [item["resourceId"] for item in response.json()["items"]]
        assert ids == [first["id"], second["id"]]

    def test_respects_limit(self, client: TestClient):
        for i in range(3):
            resource = _create_resource(client, title=f"Resource {i}")
            client.patch(f"/api/v1/resources/{resource['id']}/progress", json={"progressPercent": 10})

        response = client.get("/api/v1/resources/progress/in-progress", params={"limit": 2})
        assert len(response.json()["items"]) == 2

    def test_orphaned_progress_row_is_skipped_gracefully(
        self, client: TestClient, progress_collection, test_user_id: str
    ):
        """A progress row whose resource no longer exists (e.g. legacy data
        from before the cascade-delete existed) must never break the list
        endpoint or leak a resourceless entry."""
        from datetime import datetime, timezone

        progress_collection.insert_one(
            {
                "user_id": test_user_id,
                "resource_id": "656565656565656565656567",
                "status": "in_progress",
                "progress_percent": 50,
                "position_seconds": None,
                "duration_seconds": None,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        response = client.get("/api/v1/resources/progress/in-progress")
        assert response.status_code == 200
        assert response.json() == {"items": []}


class TestUserIsolation:
    def test_progress_never_visible_to_another_user(self, client: TestClient):
        other_headers = _second_user_headers(client)
        other_resource = client.post(
            "/api/v1/resources",
            json={"title": "Other user's video", "type": "video"},
            headers=other_headers,
        ).json()
        client.patch(
            f"/api/v1/resources/{other_resource['id']}/progress",
            json={"progressPercent": 60},
            headers=other_headers,
        )

        # The default (TEST_USER_EMAIL) caller's in-progress list never
        # includes the other user's resource.
        response = client.get("/api/v1/resources/progress/in-progress")
        assert response.json() == {"items": []}

        # Nor can the default caller read or write it directly.
        assert client.get(f"/api/v1/resources/{other_resource['id']}/progress").status_code == 404
        assert (
            client.patch(
                f"/api/v1/resources/{other_resource['id']}/progress", json={"progressPercent": 10}
            ).status_code
            == 404
        )


class TestDeletedResource:
    def test_deleting_resource_removes_progress(self, client: TestClient, progress_collection):
        resource = _create_resource(client)
        client.patch(f"/api/v1/resources/{resource['id']}/progress", json={"progressPercent": 40})
        assert progress_collection.count_documents({"resource_id": resource["id"]}) == 1

        delete_response = client.delete(f"/api/v1/resources/{resource['id']}")
        assert delete_response.status_code == 204
        assert progress_collection.count_documents({"resource_id": resource["id"]}) == 0

        assert client.get(f"/api/v1/resources/{resource['id']}/progress").status_code == 404

    def test_deleted_resource_disappears_from_in_progress_list(self, client: TestClient):
        resource = _create_resource(client)
        client.patch(f"/api/v1/resources/{resource['id']}/progress", json={"progressPercent": 40})
        assert len(client.get("/api/v1/resources/progress/in-progress").json()["items"]) == 1

        client.delete(f"/api/v1/resources/{resource['id']}")

        assert client.get("/api/v1/resources/progress/in-progress").json() == {"items": []}
