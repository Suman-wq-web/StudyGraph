import os

# Must run before `main`/`app.config` are imported anywhere, so the test suite
# never reads or writes the real development database.
os.environ.setdefault("MONGODB_DB_NAME", "studygraph_test")
# Test-only signing secret (Phase 8) -- never a real deployment's value, and
# never read from a real .env; this is the isolated test DB/environment's
# own throwaway secret, analogous to MONGODB_DB_NAME above.
os.environ.setdefault("JWT_SECRET_KEY", "test-suite-only-secret-do-not-use-in-production")
# Auto-chaining processing -> embedding is a production convenience (see
# app/config.py); tests that only exercise chunking/graph-extraction/etc.
# would otherwise unintentionally also invoke the real embedding provider
# (using whatever GEMINI_API_KEY is in backend/.env) every time they process
# a resource. Off by default here; the specific tests covering the
# auto-embed chain (tests/test_processing.py) turn it back on with their own
# monkeypatch, alongside a fake embedding provider.
os.environ.setdefault("AUTO_EMBED_AFTER_PROCESSING", "false")

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.config import settings
from app.db.collections import CONCEPTS, DOCUMENT_CHUNKS, EDGES, RESOURCE_PROGRESS, RESOURCES, USERS
from main import app

# One consistent throwaway account the `client`/`test_user_id` fixtures use
# every test -- cleaned via clean_collections like every other collection,
# so it never leaks between tests despite being "the same" email each time.
TEST_USER_EMAIL = "test-suite-user@example.com"
TEST_USER_PASSWORD = "test-suite-password-123"


@pytest.fixture
def client():
    """An authenticated TestClient: registers/logs in TEST_USER_EMAIL once
    and pre-attaches its bearer token to every request this fixture makes,
    so existing test bodies (written before Phase 8 auth) don't each need
    their own login step. See test_user_id for the matching user id, for
    tests that also call repository/service functions directly."""
    with TestClient(app) as test_client:
        test_client.post(
            "/api/v1/auth/register",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
        )
        login = test_client.post(
            "/api/v1/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
        )
        token = login.json()["accessToken"]
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client


@pytest.fixture
def test_user_id(client: TestClient) -> str:
    """The id of `client`'s authenticated user -- for tests that mix the
    HTTP client with direct repository/service calls needing a matching
    user_id (see test_search.py, test_retrieval.py, etc.)."""
    return client.get("/api/v1/auth/me").json()["id"]


@pytest.fixture(autouse=True)
def clean_collections():
    """Keep `resources`, `document_chunks`, `concepts`, `edges`,
    `resource_progress`, and `users` empty before and after every test."""
    sync_client: MongoClient = MongoClient(settings.mongodb_uri)
    db = sync_client[settings.mongodb_db_name]
    for collection_name in (RESOURCES, DOCUMENT_CHUNKS, CONCEPTS, EDGES, RESOURCE_PROGRESS, USERS):
        db[collection_name].delete_many({})
    yield
    for collection_name in (RESOURCES, DOCUMENT_CHUNKS, CONCEPTS, EDGES, RESOURCE_PROGRESS, USERS):
        db[collection_name].delete_many({})
    sync_client.close()


@pytest.fixture
def chunks_collection():
    """Direct (sync) handle to the test `document_chunks` collection, for
    assertions that don't go through the API (e.g. verifying resource_id
    linkage or absence of duplicate chunks after re-processing)."""
    sync_client: MongoClient = MongoClient(settings.mongodb_uri)
    collection = sync_client[settings.mongodb_db_name][DOCUMENT_CHUNKS]
    yield collection
    sync_client.close()


@pytest.fixture
def concepts_collection():
    """Direct (sync) handle to the test `concepts` collection."""
    sync_client: MongoClient = MongoClient(settings.mongodb_uri)
    collection = sync_client[settings.mongodb_db_name][CONCEPTS]
    yield collection
    sync_client.close()


@pytest.fixture
def edges_collection():
    """Direct (sync) handle to the test `edges` collection."""
    sync_client: MongoClient = MongoClient(settings.mongodb_uri)
    collection = sync_client[settings.mongodb_db_name][EDGES]
    yield collection
    sync_client.close()


@pytest.fixture
def users_collection():
    """Direct (sync) handle to the test `users` collection."""
    sync_client: MongoClient = MongoClient(settings.mongodb_uri)
    collection = sync_client[settings.mongodb_db_name][USERS]
    yield collection
    sync_client.close()


@pytest.fixture
def progress_collection():
    """Direct (sync) handle to the test `resource_progress` collection."""
    sync_client: MongoClient = MongoClient(settings.mongodb_uri)
    collection = sync_client[settings.mongodb_db_name][RESOURCE_PROGRESS]
    yield collection
    sync_client.close()
