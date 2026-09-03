import pytest
from fastapi.testclient import TestClient

import app.core.google_auth as google_auth_module
import app.services.auth_service as auth_service_module
from app.config import settings
from app.core.google_auth import GoogleAuthError, GoogleIdentity


def _fake_identity(*, sub="google-sub-123", email="googler@example.com", name="Ada Googler"):
    return GoogleIdentity(subject=sub, email=email, name=name)


class TestRegisterLoginMe:
    def test_register_returns_public_user_without_name(self, client: TestClient):
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "new-user@example.com", "password": "a-strong-password"},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["email"] == "new-user@example.com"
        assert body["name"] is None
        assert "hashedPassword" not in body

    def test_me_returns_authenticated_user(self, client: TestClient):
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["email"] == "test-suite-user@example.com"
        assert body["name"] is None

    def test_me_without_token_is_rejected(self):
        from main import app

        with TestClient(app) as anon_client:
            response = anon_client.get("/api/v1/auth/me")
        assert response.status_code == 401


class TestUpdateProfile:
    def test_update_name(self, client: TestClient):
        response = client.patch("/api/v1/auth/me", json={"name": "Ada Lovelace"})
        assert response.status_code == 200, response.text
        assert response.json()["name"] == "Ada Lovelace"

        # Persisted -- a follow-up GET /me reflects the change.
        me = client.get("/api/v1/auth/me")
        assert me.json()["name"] == "Ada Lovelace"

    def test_update_name_trims_whitespace(self, client: TestClient):
        response = client.patch("/api/v1/auth/me", json={"name": "  Grace Hopper  "})
        assert response.status_code == 200, response.text
        assert response.json()["name"] == "Grace Hopper"

    def test_clear_name_with_null(self, client: TestClient):
        client.patch("/api/v1/auth/me", json={"name": "Temporary"})
        response = client.patch("/api/v1/auth/me", json={"name": None})
        assert response.status_code == 200, response.text
        assert response.json()["name"] is None

    def test_name_too_long_is_rejected(self, client: TestClient):
        response = client.patch("/api/v1/auth/me", json={"name": "x" * 101})
        assert response.status_code == 422

    def test_update_requires_auth(self):
        from main import app

        with TestClient(app) as anon_client:
            response = anon_client.patch("/api/v1/auth/me", json={"name": "Nope"})
        assert response.status_code == 401

    def test_update_does_not_change_email(self, client: TestClient):
        client.patch("/api/v1/auth/me", json={"name": "Ada"})
        me = client.get("/api/v1/auth/me")
        assert me.json()["email"] == "test-suite-user@example.com"


class TestGoogleIdTokenVerification:
    """Unit tests for app/core/google_auth.py, which never makes a real
    network call in tests -- `verify_oauth2_token` (the only function that
    talks to Google) is monkeypatched to return a controlled payload, so
    these exercise this module's own claim checks in isolation."""

    def test_valid_token_returns_identity(self, monkeypatch):
        monkeypatch.setattr(settings, "google_client_id", "test-client-id.apps.googleusercontent.com")
        monkeypatch.setattr(
            google_auth_module.google_id_token,
            "verify_oauth2_token",
            lambda *a, **k: {
                "sub": "google-sub-1",
                "email": "verified@example.com",
                "email_verified": True,
                "name": "Verified Googler",
            },
        )
        identity = google_auth_module.verify_google_id_token("fake-credential")
        assert identity.subject == "google-sub-1"
        assert identity.email == "verified@example.com"
        assert identity.name == "Verified Googler"

    def test_email_normalized_to_lowercase(self, monkeypatch):
        monkeypatch.setattr(settings, "google_client_id", "test-client-id.apps.googleusercontent.com")
        monkeypatch.setattr(
            google_auth_module.google_id_token,
            "verify_oauth2_token",
            lambda *a, **k: {
                "sub": "google-sub-1",
                "email": "Mixed.Case@Example.com",
                "email_verified": True,
                "name": None,
            },
        )
        identity = google_auth_module.verify_google_id_token("fake-credential")
        assert identity.email == "mixed.case@example.com"

    def test_unverified_email_is_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "google_client_id", "test-client-id.apps.googleusercontent.com")
        monkeypatch.setattr(
            google_auth_module.google_id_token,
            "verify_oauth2_token",
            lambda *a, **k: {
                "sub": "google-sub-1",
                "email": "unverified@example.com",
                "email_verified": False,
                "name": "Unverified",
            },
        )
        with pytest.raises(GoogleAuthError):
            google_auth_module.verify_google_id_token("fake-credential")

    def test_invalid_credential_is_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "google_client_id", "test-client-id.apps.googleusercontent.com")

        def _raise(*a, **k):
            raise ValueError("Token used too early")

        monkeypatch.setattr(google_auth_module.google_id_token, "verify_oauth2_token", _raise)
        with pytest.raises(GoogleAuthError):
            google_auth_module.verify_google_id_token("tampered-credential")

    def test_missing_client_id_config_is_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "google_client_id", "")
        with pytest.raises(GoogleAuthError):
            google_auth_module.verify_google_id_token("fake-credential")


class TestGoogleLogin:
    """API-level tests for POST /api/v1/auth/google. `auth_service`'s
    `verify_google_id_token` is monkeypatched to a canned GoogleIdentity so
    these exercise routing/user-lookup/token-issuance without depending on
    app/core/google_auth.py's own claim-checking logic (covered above)."""

    def test_new_google_user_is_created(self, client: TestClient, users_collection, monkeypatch):
        monkeypatch.setattr(
            auth_service_module,
            "verify_google_id_token",
            lambda credential: _fake_identity(
                sub="google-sub-new", email="brand-new-googler@example.com", name="New Googler"
            ),
        )
        response = client.post("/api/v1/auth/google", json={"credential": "fake-credential"})
        assert response.status_code == 200, response.text
        token = response.json()["accessToken"]

        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.json()["email"] == "brand-new-googler@example.com"
        assert me.json()["name"] == "New Googler"

        assert users_collection.count_documents({"email": "brand-new-googler@example.com"}) == 1

    def test_google_login_is_rejected_for_existing_password_account(
        self, client: TestClient, users_collection, monkeypatch
    ):
        """Security regression (pre-account-hijacking fix): a Google sign-in
        must never auto-link onto -- or log into -- an existing
        password-only account just because the email matches. Previously
        this silently linked and logged in as the existing account; now it
        must be rejected and the account left completely untouched."""
        register = client.post(
            "/api/v1/auth/register",
            json={"email": "existing-user@example.com", "password": "existing-password-1"},
        )
        assert register.status_code == 201, register.text
        existing_id = register.json()["id"]

        monkeypatch.setattr(
            auth_service_module,
            "verify_google_id_token",
            lambda credential: _fake_identity(
                sub="google-sub-existing", email="existing-user@example.com", name="Existing User"
            ),
        )
        response = client.post("/api/v1/auth/google", json={"credential": "fake-credential"})
        assert response.status_code == 401
        # Same generic message as any other invalid Google credential -- must
        # not reveal that this email belongs to a password-only account.
        assert response.json()["detail"] == "Invalid Google credential."

        # No duplicate, and the existing account is completely unmodified --
        # no google_id was attached, hashed_password is untouched.
        assert users_collection.count_documents({"email": "existing-user@example.com"}) == 1
        doc = users_collection.find_one({"email": "existing-user@example.com"})
        assert str(doc["_id"]) == existing_id
        assert doc.get("google_id") is None
        assert doc["hashed_password"] is not None

        # The original password still logs in -- the account was never
        # touched by the rejected Google attempt.
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "existing-user@example.com", "password": "existing-password-1"},
        )
        assert login.status_code == 200, login.text

    def test_google_login_is_rejected_for_mismatched_google_id(
        self, client: TestClient, users_collection, monkeypatch
    ):
        """Security regression: an email that already belongs to an account
        linked to a DIFFERENT google_id must be rejected, not silently
        re-linked to the new google_id."""
        monkeypatch.setattr(
            auth_service_module,
            "verify_google_id_token",
            lambda credential: _fake_identity(
                sub="google-sub-original", email="dual-identity@example.com", name="Original"
            ),
        )
        first = client.post("/api/v1/auth/google", json={"credential": "fake-credential"})
        assert first.status_code == 200, first.text
        original_id = first.json()["accessToken"]

        monkeypatch.setattr(
            auth_service_module,
            "verify_google_id_token",
            lambda credential: _fake_identity(
                sub="google-sub-different", email="dual-identity@example.com", name="Different"
            ),
        )
        second = client.post("/api/v1/auth/google", json={"credential": "fake-credential"})
        assert second.status_code == 401
        assert second.json()["detail"] == "Invalid Google credential."

        # Still exactly one account, still linked to the ORIGINAL google_id --
        # the mismatched attempt must not have overwritten it.
        assert users_collection.count_documents({"email": "dual-identity@example.com"}) == 1
        doc = users_collection.find_one({"email": "dual-identity@example.com"})
        assert doc["google_id"] == "google-sub-original"

        # The original identity can still log in normally.
        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {original_id}"})
        assert me.status_code == 200

    def test_google_login_succeeds_for_repeat_same_google_identity(
        self, client: TestClient, users_collection, monkeypatch
    ):
        """Legitimate flow must keep working: signing in again with the SAME
        google_id that's already linked to the account logs in as that
        account (not rejected, not duplicated)."""
        monkeypatch.setattr(
            auth_service_module,
            "verify_google_id_token",
            lambda credential: _fake_identity(
                sub="google-sub-repeat", email="repeat-googler@example.com", name="Repeat Googler"
            ),
        )
        first = client.post("/api/v1/auth/google", json={"credential": "fake-credential"})
        assert first.status_code == 200, first.text
        first_id = first.json()["accessToken"]

        second = client.post("/api/v1/auth/google", json={"credential": "fake-credential"})
        assert second.status_code == 200, second.text

        me_first = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {first_id}"})
        me_second = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {second.json()['accessToken']}"}
        )
        assert me_first.json()["id"] == me_second.json()["id"]
        assert users_collection.count_documents({"email": "repeat-googler@example.com"}) == 1

    def test_invalid_google_token_is_rejected(self, client: TestClient, monkeypatch):
        def _raise(credential):
            raise GoogleAuthError("Invalid Google credential.")

        monkeypatch.setattr(auth_service_module, "verify_google_id_token", _raise)
        response = client.post("/api/v1/auth/google", json={"credential": "tampered"})
        assert response.status_code == 401

    def test_password_login_is_refused_for_google_only_account(
        self, client: TestClient, users_collection, monkeypatch
    ):
        monkeypatch.setattr(
            auth_service_module,
            "verify_google_id_token",
            lambda credential: _fake_identity(
                sub="google-sub-only", email="google-only@example.com", name="Google Only"
            ),
        )
        created = client.post("/api/v1/auth/google", json={"credential": "fake-credential"})
        assert created.status_code == 200, created.text

        # No password was ever set for this account -- any password attempt
        # must fail with the same generic 401 as a wrong-password attempt,
        # never a crash and never a hint that this is a Google-only account.
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "google-only@example.com", "password": "some-guessed-password"},
        )
        assert response.status_code == 401

    def test_missing_credential_is_a_validation_error(self, client: TestClient):
        response = client.post("/api/v1/auth/google", json={})
        assert response.status_code == 422
