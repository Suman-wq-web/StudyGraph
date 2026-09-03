"""
Tests for app/db/concept_repository.py -- plain find/insert/find_one_and_update
against the local test MongoDB (no Atlas features needed).
"""

import asyncio

from app.db import concept_repository, mongodb


def _run_with_db(coro_fn):
    """Same pattern as test_chunk_repository.py: isolates this test's Mongo
    connection on its own event loop, independent of the `client` fixture's."""

    async def _wrapped():
        mongodb.connect()
        try:
            return await coro_fn()
        finally:
            mongodb.close()

    return asyncio.run(_wrapped())


class TestCreateAndFind:
    def test_create_then_find_by_normalized_name(self):
        async def scenario():
            created = await concept_repository.create(
                user_id="u1",
                name="Gradient Descent",
                normalized_name="gradient descent",
                description="an optimization algorithm",
                source_resource_id="r1",
            )
            found = await concept_repository.find_by_normalized_name("u1", "gradient descent")
            return created, found

        created, found = _run_with_db(scenario)
        assert found is not None
        assert found.id == created.id
        assert found.source_resource_ids == ["r1"]
        assert found.aliases == []

    def test_find_by_normalized_name_is_scoped_by_user(self):
        async def scenario():
            await concept_repository.create(
                user_id="u1", name="X", normalized_name="x", description=None, source_resource_id="r1"
            )
            return await concept_repository.find_by_normalized_name("u2", "x")

        assert _run_with_db(scenario) is None

    def test_find_by_normalized_name_missing_returns_none(self):
        assert _run_with_db(lambda: concept_repository.find_by_normalized_name("u1", "nope")) is None


class TestAddSourceResource:
    def test_adds_new_resource_id(self):
        async def scenario():
            created = await concept_repository.create(
                user_id="u1", name="X", normalized_name="x", description=None, source_resource_id="r1"
            )
            return await concept_repository.add_source_resource(created.id, "r2")

        updated = _run_with_db(scenario)
        assert set(updated.source_resource_ids) == {"r1", "r2"}

    def test_adding_duplicate_resource_id_is_a_noop(self):
        async def scenario():
            created = await concept_repository.create(
                user_id="u1", name="X", normalized_name="x", description=None, source_resource_id="r1"
            )
            return await concept_repository.add_source_resource(created.id, "r1")

        updated = _run_with_db(scenario)
        assert updated.source_resource_ids == ["r1"]

    def test_unknown_concept_id_returns_none(self):
        result = _run_with_db(
            lambda: concept_repository.add_source_resource("000000000000000000000000", "r1")
        )
        assert result is None


class TestListByUser:
    def test_lists_only_that_users_concepts(self):
        async def scenario():
            await concept_repository.create(
                user_id="u1", name="A", normalized_name="a", description=None, source_resource_id="r1"
            )
            await concept_repository.create(
                user_id="u2", name="B", normalized_name="b", description=None, source_resource_id="r1"
            )
            return await concept_repository.list_by_user("u1")

        result = _run_with_db(scenario)
        assert [c.name for c in result] == ["A"]


class TestSetCentralityScores:
    def test_writes_scores_by_concept_id(self):
        async def scenario():
            created = await concept_repository.create(
                user_id="u1", name="A", normalized_name="a", description=None, source_resource_id="r1"
            )
            await concept_repository.set_centrality_scores({created.id: 0.42})
            return await concept_repository.find_by_normalized_name("u1", "a")

        result = _run_with_db(scenario)
        assert result.centrality_score == 0.42

    def test_unknown_concept_id_is_skipped_without_raising(self):
        _run_with_db(
            lambda: concept_repository.set_centrality_scores({"000000000000000000000000": 1.0})
        )
