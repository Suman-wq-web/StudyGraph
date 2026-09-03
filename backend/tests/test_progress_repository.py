"""
Tests for app/db/progress_repository.py -- plain upsert/find/delete against
the local test MongoDB. Same pattern as test_concept_repository.py.
"""

import asyncio

from app.db import mongodb, progress_repository


def _run_with_db(coro_fn):
    """Same pattern as test_concept_repository.py: isolates this test's
    Mongo connection on its own event loop, independent of the `client`
    fixture's."""

    async def _wrapped():
        mongodb.connect()
        try:
            return await coro_fn()
        finally:
            mongodb.close()

    return asyncio.run(_wrapped())


class TestUpsert:
    def test_first_upsert_creates_a_row(self):
        async def scenario():
            return await progress_repository.upsert(
                user_id="u1",
                resource_id="r1",
                changes={"status": "in_progress", "progress_percent": 10.0},
            )

        result = _run_with_db(scenario)
        assert result.id is not None
        assert result.user_id == "u1"
        assert result.resource_id == "r1"
        assert result.status == "in_progress"
        assert result.progress_percent == 10.0
        assert result.created_at == result.updated_at

    def test_repeated_upsert_updates_the_same_row(self):
        async def scenario():
            first = await progress_repository.upsert(
                user_id="u1", resource_id="r1", changes={"status": "in_progress", "progress_percent": 10.0}
            )
            second = await progress_repository.upsert(
                user_id="u1", resource_id="r1", changes={"status": "in_progress", "progress_percent": 55.0}
            )
            return first, second

        first, second = _run_with_db(scenario)
        assert first.id == second.id
        assert second.progress_percent == 55.0
        assert second.created_at == first.created_at
        assert second.updated_at >= first.updated_at

    def test_upsert_is_scoped_per_user_even_for_the_same_resource(self):
        async def scenario():
            await progress_repository.upsert(
                user_id="u1", resource_id="r1", changes={"status": "in_progress", "progress_percent": 10.0}
            )
            await progress_repository.upsert(
                user_id="u2", resource_id="r1", changes={"status": "in_progress", "progress_percent": 90.0}
            )
            u1 = await progress_repository.get(user_id="u1", resource_id="r1")
            u2 = await progress_repository.get(user_id="u2", resource_id="r1")
            return u1, u2

        u1, u2 = _run_with_db(scenario)
        assert u1.progress_percent == 10.0
        assert u2.progress_percent == 90.0


class TestGet:
    def test_missing_row_returns_none(self):
        result = _run_with_db(lambda: progress_repository.get(user_id="u1", resource_id="nope"))
        assert result is None


class TestListInProgress:
    def test_only_in_progress_rows_are_returned(self):
        async def scenario():
            await progress_repository.upsert(
                user_id="u1", resource_id="r1", changes={"status": "in_progress", "progress_percent": 10.0}
            )
            await progress_repository.upsert(
                user_id="u1", resource_id="r2", changes={"status": "completed", "progress_percent": 100.0}
            )
            await progress_repository.upsert(
                user_id="u1", resource_id="r3", changes={"status": "not_started", "progress_percent": 0.0}
            )
            return await progress_repository.list_in_progress(user_id="u1")

        result = _run_with_db(scenario)
        assert [doc.resource_id for doc in result] == ["r1"]

    def test_respects_limit(self):
        async def scenario():
            for i in range(5):
                await progress_repository.upsert(
                    user_id="u1",
                    resource_id=f"r{i}",
                    changes={"status": "in_progress", "progress_percent": 10.0},
                )
            return await progress_repository.list_in_progress(user_id="u1", limit=2)

        result = _run_with_db(scenario)
        assert len(result) == 2


class TestDeleteByResource:
    def test_deletes_the_row_for_that_resource(self):
        async def scenario():
            await progress_repository.upsert(
                user_id="u1", resource_id="r1", changes={"status": "in_progress", "progress_percent": 10.0}
            )
            deleted_count = await progress_repository.delete_by_resource("r1")
            remaining = await progress_repository.get(user_id="u1", resource_id="r1")
            return deleted_count, remaining

        deleted_count, remaining = _run_with_db(scenario)
        assert deleted_count == 1
        assert remaining is None

    def test_unknown_resource_id_deletes_nothing(self):
        deleted_count = _run_with_db(lambda: progress_repository.delete_by_resource("nope"))
        assert deleted_count == 0
