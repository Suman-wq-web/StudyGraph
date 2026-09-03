"""
Tests for hybrid retrieval (app/services/rag/retrieval.py). No real Gemini
calls and no real Atlas $vectorSearch/$search -- chunk_repository's
vector_search/text_search/get_many_by_ids are all mocked/injected, mirroring
test_search.py's approach for the vector-only search service.

Since Phase 8, `_resolve_resource_ids` always resolves a user_id-scoped
allowlist -- even with no type/tag filter -- so most scenarios here need a
real resource to exist for the test user (via resource_repository.create)
before the mocked chunk_repository functions are ever reached; otherwise
hybrid_search short-circuits to `[]` before calling either retriever. This
mirrors test_search.py's `test_no_type_tag_filter_still_restricts_to_the_
callers_own_resources` and its "A resource must exist for this user, or ...
would short-circuit" comments.
"""

import asyncio
from datetime import datetime, timezone

import pytest

from app.db import chunk_repository, mongodb, resource_repository
from app.models.chunk import DocumentChunk
from app.models.resource import ResourceCreate, ResourceType
from app.services.rag import retrieval
from app.services.rag.embeddings import EmbeddingProvider, EmbeddingProviderError, EmbeddingVector

_TEST_USER_ID = "test-retrieval-user"
_OTHER_USER_ID = "test-retrieval-other-user"


class FakeEmbeddingProvider(EmbeddingProvider):
    def __init__(self, vector: list[float] | None = None):
        self._vector = vector or [0.1, 0.2, 0.3]
        self.queries: list[str] = []

    @property
    def model_name(self) -> str:
        return "fake-embedding-model"

    async def embed_documents(self, texts):
        raise NotImplementedError("not used by retrieval")

    async def embed_query(self, text: str) -> EmbeddingVector:
        self.queries.append(text)
        return EmbeddingVector(values=self._vector, dimensions=len(self._vector))


def _run_with_db(coro_fn):
    """Same pattern as test_search.py: isolates this test's Mongo connection
    on its own event loop, independent of the `client` fixture's."""

    async def _wrapped():
        mongodb.connect()
        try:
            return await coro_fn()
        finally:
            mongodb.close()

    return asyncio.run(_wrapped())


async def _create_resource(user_id: str = _TEST_USER_ID, **overrides):
    payload = {"title": "A note", "type": ResourceType.NOTE, "content": "x", **overrides}
    return await resource_repository.create(ResourceCreate(**payload), user_id)


def _make_chunk(
    chunk_id: str,
    *,
    resource_id: str = "r1",
    text: str = "text",
    chunk_index: int = 0,
    user_id: str = _TEST_USER_ID,
) -> DocumentChunk:
    now = datetime.now(timezone.utc)
    return DocumentChunk(
        id=chunk_id,
        user_id=user_id,
        resource_id=resource_id,
        chunk_index=chunk_index,
        text=text,
        token_count=1,
        start_token=0,
        end_token=1,
        created_at=now,
        updated_at=now,
    )


class TestReciprocalRankFusion:
    def test_item_in_both_lists_ranks_above_item_in_one(self):
        fused = retrieval._reciprocal_rank_fusion([["a", "b"], ["a", "c"]], k=60)
        fused_ids = [chunk_id for chunk_id, _ in fused]
        assert fused_ids[0] == "a"
        assert set(fused_ids[1:]) == {"b", "c"}

    def test_tie_broken_by_tiebreak_score_descending(self):
        fused = retrieval._reciprocal_rank_fusion(
            [["x"], ["y"]], k=60, tiebreak_scores={"x": 0.1, "y": 0.9}
        )
        assert [chunk_id for chunk_id, _ in fused] == ["y", "x"]

    def test_tie_broken_by_id_ascending_when_no_tiebreak_score(self):
        fused = retrieval._reciprocal_rank_fusion([["b"], ["a"]], k=60)
        assert [chunk_id for chunk_id, _ in fused] == ["a", "b"]

    def test_id_absent_from_a_list_contributes_nothing_from_it(self):
        fused = retrieval._reciprocal_rank_fusion([["a"], []], k=60)
        assert dict(fused)["a"] == pytest.approx(1 / 61)


class TestHybridSearchFusion:
    def test_combines_both_retrievers_and_returns_full_chunks(self, monkeypatch):
        chunk_a = _make_chunk("656565656565656565656561", text="chunk a")
        chunk_b = _make_chunk("656565656565656565656562", text="chunk b")

        async def fake_vector_search(query_vector, *, top_k, resource_ids=None, num_candidates=None):
            return [{"id": chunk_a.id, "score": 0.9}]

        async def fake_text_search(query, *, top_k, resource_ids=None):
            return [{"id": chunk_b.id, "score": 5.0}]

        async def fake_get_many_by_ids(ids, user_id):
            assert user_id == _TEST_USER_ID
            by_id = {chunk_a.id: chunk_a, chunk_b.id: chunk_b}
            return [by_id[i] for i in ids if i in by_id]

        async def scenario():
            # A resource must exist for this user, or hybrid_search would
            # short-circuit on the (always-applied, Phase 8) user scope
            # before ever reaching the mocks below.
            await _create_resource()
            monkeypatch.setattr(chunk_repository, "vector_search", fake_vector_search)
            monkeypatch.setattr(chunk_repository, "text_search", fake_text_search)
            monkeypatch.setattr(chunk_repository, "get_many_by_ids", fake_get_many_by_ids)

            filters = retrieval.RetrievalFilters(user_id=_TEST_USER_ID)
            return await retrieval.hybrid_search(
                "query", filters, top_k=8, embedding_provider=FakeEmbeddingProvider()
            )

        result = _run_with_db(scenario)

        assert {chunk.id for chunk in result} == {chunk_a.id, chunk_b.id}

    def test_result_truncated_to_top_k(self, monkeypatch):
        chunks = [_make_chunk(f"65656565656565656565656{i}") for i in range(5)]

        async def fake_vector_search(query_vector, *, top_k, resource_ids=None, num_candidates=None):
            return [{"id": c.id, "score": 1.0 - i * 0.1} for i, c in enumerate(chunks)]

        async def fake_text_search(query, *, top_k, resource_ids=None):
            return []

        async def fake_get_many_by_ids(ids, user_id):
            by_id = {c.id: c for c in chunks}
            return [by_id[i] for i in ids if i in by_id]

        async def scenario():
            await _create_resource()
            monkeypatch.setattr(chunk_repository, "vector_search", fake_vector_search)
            monkeypatch.setattr(chunk_repository, "text_search", fake_text_search)
            monkeypatch.setattr(chunk_repository, "get_many_by_ids", fake_get_many_by_ids)

            filters = retrieval.RetrievalFilters(user_id=_TEST_USER_ID)
            return await retrieval.hybrid_search(
                "query", filters, top_k=2, embedding_provider=FakeEmbeddingProvider()
            )

        result = _run_with_db(scenario)

        assert len(result) == 2


class TestPartialFailureHandling:
    def test_vector_side_failure_degrades_to_text_side(self, monkeypatch):
        chunk = _make_chunk("656565656565656565656563")

        async def failing_vector_search(*args, **kwargs):
            raise RuntimeError("$vectorSearch is not supported")

        async def fake_text_search(query, *, top_k, resource_ids=None):
            return [{"id": chunk.id, "score": 1.0}]

        async def fake_get_many_by_ids(ids, user_id):
            return [chunk] if chunk.id in ids else []

        async def scenario():
            await _create_resource()
            monkeypatch.setattr(chunk_repository, "vector_search", failing_vector_search)
            monkeypatch.setattr(chunk_repository, "text_search", fake_text_search)
            monkeypatch.setattr(chunk_repository, "get_many_by_ids", fake_get_many_by_ids)

            filters = retrieval.RetrievalFilters(user_id=_TEST_USER_ID)
            return await retrieval.hybrid_search(
                "query", filters, embedding_provider=FakeEmbeddingProvider()
            )

        result = _run_with_db(scenario)
        assert [c.id for c in result] == [chunk.id]

    def test_text_side_failure_degrades_to_vector_side(self, monkeypatch):
        chunk = _make_chunk("656565656565656565656564")

        async def fake_vector_search(query_vector, *, top_k, resource_ids=None, num_candidates=None):
            return [{"id": chunk.id, "score": 0.5}]

        async def failing_text_search(*args, **kwargs):
            raise RuntimeError("$search index not found")

        async def fake_get_many_by_ids(ids, user_id):
            return [chunk] if chunk.id in ids else []

        async def scenario():
            await _create_resource()
            monkeypatch.setattr(chunk_repository, "vector_search", fake_vector_search)
            monkeypatch.setattr(chunk_repository, "text_search", failing_text_search)
            monkeypatch.setattr(chunk_repository, "get_many_by_ids", fake_get_many_by_ids)

            filters = retrieval.RetrievalFilters(user_id=_TEST_USER_ID)
            return await retrieval.hybrid_search(
                "query", filters, embedding_provider=FakeEmbeddingProvider()
            )

        result = _run_with_db(scenario)
        assert [c.id for c in result] == [chunk.id]

    def test_both_sides_failing_raises_retrieval_unavailable(self, monkeypatch):
        async def failing_vector_search(*args, **kwargs):
            raise RuntimeError("$vectorSearch is not supported")

        async def failing_text_search(*args, **kwargs):
            raise RuntimeError("$search index not found")

        async def scenario():
            await _create_resource()
            monkeypatch.setattr(chunk_repository, "vector_search", failing_vector_search)
            monkeypatch.setattr(chunk_repository, "text_search", failing_text_search)

            filters = retrieval.RetrievalFilters(user_id=_TEST_USER_ID)
            await retrieval.hybrid_search(
                "query", filters, embedding_provider=FakeEmbeddingProvider()
            )

        with pytest.raises(retrieval.RetrievalUnavailableError):
            _run_with_db(scenario)

    def test_embedding_failure_degrades_to_text_side(self, monkeypatch):
        chunk = _make_chunk("656565656565656565656565")

        class FailingProvider(FakeEmbeddingProvider):
            async def embed_query(self, text: str):
                raise EmbeddingProviderError("Gemini rejected the request")

        async def fake_text_search(query, *, top_k, resource_ids=None):
            return [{"id": chunk.id, "score": 1.0}]

        async def fake_get_many_by_ids(ids, user_id):
            return [chunk] if chunk.id in ids else []

        async def scenario():
            await _create_resource()
            monkeypatch.setattr(chunk_repository, "text_search", fake_text_search)
            monkeypatch.setattr(chunk_repository, "get_many_by_ids", fake_get_many_by_ids)

            filters = retrieval.RetrievalFilters(user_id=_TEST_USER_ID)
            return await retrieval.hybrid_search(
                "query", filters, embedding_provider=FailingProvider()
            )

        result = _run_with_db(scenario)
        assert [c.id for c in result] == [chunk.id]


class TestCandidatePoolSizing:
    def test_retrievers_are_queried_for_candidate_pool_not_raw_top_k(self, monkeypatch):
        captured: dict = {}

        async def fake_vector_search(query_vector, *, top_k, resource_ids=None, num_candidates=None):
            captured["vector_top_k"] = top_k
            return []

        async def fake_text_search(query, *, top_k, resource_ids=None):
            captured["text_top_k"] = top_k
            return []

        async def scenario():
            await _create_resource()
            monkeypatch.setattr(chunk_repository, "vector_search", fake_vector_search)
            monkeypatch.setattr(chunk_repository, "text_search", fake_text_search)

            filters = retrieval.RetrievalFilters(user_id=_TEST_USER_ID)
            await retrieval.hybrid_search(
                "query", filters, top_k=2, embedding_provider=FakeEmbeddingProvider()
            )

        _run_with_db(scenario)

        # default settings: max(2 * 4, 20) == 20
        assert captured["vector_top_k"] == 20
        assert captured["text_top_k"] == 20


class TestMetadataFiltering:
    def test_resource_type_resolves_to_shared_allowlist_for_both_retrievers(self, monkeypatch):
        captured: dict = {}

        async def fake_vector_search(query_vector, *, top_k, resource_ids=None, num_candidates=None):
            captured["vector_resource_ids"] = resource_ids
            return []

        async def fake_text_search(query, *, top_k, resource_ids=None):
            captured["text_resource_ids"] = resource_ids
            return []

        async def scenario():
            note = await _create_resource(title="A note", type=ResourceType.NOTE, content="x")
            await _create_resource(
                title="An article",
                type=ResourceType.ARTICLE,
                source_url="https://example.com",
                content="x",
            )
            monkeypatch.setattr(chunk_repository, "vector_search", fake_vector_search)
            monkeypatch.setattr(chunk_repository, "text_search", fake_text_search)

            filters = retrieval.RetrievalFilters(user_id=_TEST_USER_ID, resource_types=["note"])
            await retrieval.hybrid_search("query", filters, embedding_provider=FakeEmbeddingProvider())
            return note

        note = _run_with_db(scenario)
        assert captured["vector_resource_ids"] == [note.id]
        assert captured["text_resource_ids"] == [note.id]

    def test_no_matching_resources_short_circuits_both_retrievers(self, monkeypatch):
        called = False

        async def fake_vector_search(*args, **kwargs):
            nonlocal called
            called = True
            return []

        async def fake_text_search(*args, **kwargs):
            nonlocal called
            called = True
            return []

        async def scenario():
            await _create_resource(title="A note", type=ResourceType.NOTE, content="x")
            monkeypatch.setattr(chunk_repository, "vector_search", fake_vector_search)
            monkeypatch.setattr(chunk_repository, "text_search", fake_text_search)

            filters = retrieval.RetrievalFilters(user_id=_TEST_USER_ID, resource_types=["video"])
            return await retrieval.hybrid_search(
                "query", filters, embedding_provider=FakeEmbeddingProvider()
            )

        result = _run_with_db(scenario)
        assert called is False
        assert result == []

    def test_no_filter_still_restricts_to_the_callers_own_resources(self, monkeypatch):
        """Phase 8: unlike Phase 5, "no filter" no longer means "search
        across every user's chunks" -- the caller's own resource ids are
        always the outer bound, even with no explicit type/tag filter."""
        captured: dict = {}

        async def fake_vector_search(query_vector, *, top_k, resource_ids=None, num_candidates=None):
            captured["resource_ids"] = resource_ids
            return []

        async def fake_text_search(query, *, top_k, resource_ids=None):
            return []

        async def scenario():
            note = await _create_resource()
            monkeypatch.setattr(chunk_repository, "vector_search", fake_vector_search)
            monkeypatch.setattr(chunk_repository, "text_search", fake_text_search)

            filters = retrieval.RetrievalFilters(user_id=_TEST_USER_ID)
            await retrieval.hybrid_search("query", filters, embedding_provider=FakeEmbeddingProvider())
            return note

        note = _run_with_db(scenario)
        assert captured["resource_ids"] == [note.id]


class TestUserIsolation:
    def test_resource_allowlist_never_includes_another_users_resources(self, monkeypatch):
        """Security regression guard: even with no type/tag filter, resolving
        the pre-filter allowlist for one user must never surface another
        user's resource ids -- that would let hybrid_search's Atlas
        pre-filter (and therefore its results) leak across users."""
        captured: dict = {}

        async def fake_vector_search(query_vector, *, top_k, resource_ids=None, num_candidates=None):
            captured["resource_ids"] = resource_ids
            return []

        async def fake_text_search(query, *, top_k, resource_ids=None):
            return []

        async def scenario():
            mine = await _create_resource(user_id=_TEST_USER_ID, title="Mine")
            await _create_resource(user_id=_OTHER_USER_ID, title="Not mine")
            monkeypatch.setattr(chunk_repository, "vector_search", fake_vector_search)
            monkeypatch.setattr(chunk_repository, "text_search", fake_text_search)

            filters = retrieval.RetrievalFilters(user_id=_TEST_USER_ID)
            await retrieval.hybrid_search("query", filters, embedding_provider=FakeEmbeddingProvider())
            return mine

        mine = _run_with_db(scenario)
        assert captured["resource_ids"] == [mine.id]

    def test_chunk_fetch_never_returns_another_users_chunk_even_if_fused_in(self, monkeypatch):
        """Defense-in-depth guard for chunk_repository.get_many_by_ids's own
        user_id filter (Phase 8): even if a chunk id belonging to another
        user somehow made it through fusion, the final fetch must not return
        it."""
        my_chunk = _make_chunk("656565656565656565656566")
        other_users_chunk_id = "656565656565656565656567"

        async def fake_vector_search(query_vector, *, top_k, resource_ids=None, num_candidates=None):
            return [{"id": my_chunk.id, "score": 0.9}, {"id": other_users_chunk_id, "score": 0.8}]

        async def fake_text_search(query, *, top_k, resource_ids=None):
            return []

        async def fake_get_many_by_ids(ids, user_id):
            assert user_id == _TEST_USER_ID
            # Simulates the real repository's user_id filter: only this
            # user's own chunk comes back, regardless of what ids were asked for.
            return [my_chunk] if my_chunk.id in ids else []

        async def scenario():
            await _create_resource()
            monkeypatch.setattr(chunk_repository, "vector_search", fake_vector_search)
            monkeypatch.setattr(chunk_repository, "text_search", fake_text_search)
            monkeypatch.setattr(chunk_repository, "get_many_by_ids", fake_get_many_by_ids)

            filters = retrieval.RetrievalFilters(user_id=_TEST_USER_ID)
            return await retrieval.hybrid_search(
                "query", filters, embedding_provider=FakeEmbeddingProvider()
            )

        result = _run_with_db(scenario)
        assert [c.id for c in result] == [my_chunk.id]
