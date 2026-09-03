"""
Tests for app/db/edge_repository.py -- plain find/insert/find_one_and_update
against the local test MongoDB (no Atlas features needed).
"""

import asyncio

from app.db import edge_repository, mongodb
from app.models.edge import RelationType


def _run_with_db(coro_fn):
    async def _wrapped():
        mongodb.connect()
        try:
            return await coro_fn()
        finally:
            mongodb.close()

    return asyncio.run(_wrapped())


class TestCreateAndFind:
    def test_create_then_find_by_triple(self):
        async def scenario():
            created = await edge_repository.create(
                user_id="u1",
                source_concept_id="c1",
                target_concept_id="c2",
                relation_type=RelationType.PREREQUISITE_OF,
                evidence_chunk_id="chunk1",
            )
            found = await edge_repository.find_by_triple("u1", "c1", "c2", RelationType.PREREQUISITE_OF)
            return created, found

        created, found = _run_with_db(scenario)
        assert found is not None
        assert found.id == created.id
        assert found.weight == 1.0
        assert found.evidence_chunk_ids == ["chunk1"]

    def test_find_by_triple_distinguishes_relation_type(self):
        async def scenario():
            await edge_repository.create(
                user_id="u1",
                source_concept_id="c1",
                target_concept_id="c2",
                relation_type=RelationType.RELATED_TO,
                evidence_chunk_id="chunk1",
            )
            return await edge_repository.find_by_triple("u1", "c1", "c2", RelationType.PREREQUISITE_OF)

        assert _run_with_db(scenario) is None


class TestAddEvidence:
    def test_new_evidence_increments_weight(self):
        async def scenario():
            created = await edge_repository.create(
                user_id="u1",
                source_concept_id="c1",
                target_concept_id="c2",
                relation_type=RelationType.RELATED_TO,
                evidence_chunk_id="chunk1",
            )
            return await edge_repository.add_evidence(created.id, "chunk2")

        updated = _run_with_db(scenario)
        assert updated.weight == 2.0
        assert set(updated.evidence_chunk_ids) == {"chunk1", "chunk2"}

    def test_repeat_evidence_from_same_chunk_does_not_inflate_weight(self):
        async def scenario():
            created = await edge_repository.create(
                user_id="u1",
                source_concept_id="c1",
                target_concept_id="c2",
                relation_type=RelationType.RELATED_TO,
                evidence_chunk_id="chunk1",
            )
            return await edge_repository.add_evidence(created.id, "chunk1")

        updated = _run_with_db(scenario)
        assert updated.weight == 1.0
        assert updated.evidence_chunk_ids == ["chunk1"]

    def test_unknown_edge_id_returns_none(self):
        result = _run_with_db(lambda: edge_repository.add_evidence("000000000000000000000000", "chunk1"))
        assert result is None


class TestListByUser:
    def test_lists_only_that_users_edges(self):
        async def scenario():
            await edge_repository.create(
                user_id="u1",
                source_concept_id="c1",
                target_concept_id="c2",
                relation_type=RelationType.RELATED_TO,
                evidence_chunk_id="chunk1",
            )
            await edge_repository.create(
                user_id="u2",
                source_concept_id="c3",
                target_concept_id="c4",
                relation_type=RelationType.RELATED_TO,
                evidence_chunk_id="chunk1",
            )
            return await edge_repository.list_by_user("u1")

        result = _run_with_db(scenario)
        assert len(result) == 1
        assert result[0].source_concept_id == "c1"
