"""
Tests for app/services/graph/builder.py:build_user_graph. No DB --
monkeypatches concept_repository.list_by_user / edge_repository.list_by_user
with in-memory fixtures, keeping this test as DB-free as test_chunking.py is
for its own pure function.
"""

import asyncio
from datetime import datetime, timezone

from app.db import concept_repository, edge_repository
from app.models.concept import Concept
from app.models.edge import ConceptEdge, RelationType
from app.services.graph import builder


def _async_return(value):
    async def _fn(*args, **kwargs):
        return value

    return _fn


def _concept(id_: str, name: str, **overrides) -> Concept:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=id_,
        user_id="u1",
        name=name,
        normalized_name=name.lower(),
        description=None,
        aliases=[],
        source_resource_ids=["r1"],
        centrality_score=None,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return Concept(**defaults)


def _edge(id_: str, source: str, target: str, relation_type=RelationType.RELATED_TO, weight: float = 1.0) -> ConceptEdge:
    return ConceptEdge(
        id=id_,
        user_id="u1",
        source_concept_id=source,
        target_concept_id=target,
        relation_type=relation_type,
        weight=weight,
        evidence_chunk_ids=["chunk1"],
        created_at=datetime.now(timezone.utc),
    )


class TestBuildUserGraph:
    def test_nodes_and_edges_are_added_with_attributes(self, monkeypatch):
        concepts = [_concept("c1", "A"), _concept("c2", "B")]
        edges = [_edge("e1", "c1", "c2", RelationType.PREREQUISITE_OF, weight=2.0)]
        monkeypatch.setattr(concept_repository, "list_by_user", _async_return(concepts))
        monkeypatch.setattr(edge_repository, "list_by_user", _async_return(edges))

        graph = asyncio.run(builder.build_user_graph("u1"))

        assert set(graph.nodes) == {"c1", "c2"}
        assert graph.nodes["c1"]["name"] == "A"
        assert graph.has_edge("c1", "c2")
        assert graph["c1"]["c2"]["relation_type"] == "prerequisite_of"
        assert graph["c1"]["c2"]["weight"] == 2.0

    def test_edge_with_dangling_reference_is_skipped(self, monkeypatch):
        concepts = [_concept("c1", "A")]
        edges = [_edge("e1", "c1", "missing")]
        monkeypatch.setattr(concept_repository, "list_by_user", _async_return(concepts))
        monkeypatch.setattr(edge_repository, "list_by_user", _async_return(edges))

        graph = asyncio.run(builder.build_user_graph("u1"))

        assert graph.number_of_edges() == 0

    def test_empty_user_returns_empty_graph(self, monkeypatch):
        monkeypatch.setattr(concept_repository, "list_by_user", _async_return([]))
        monkeypatch.setattr(edge_repository, "list_by_user", _async_return([]))

        graph = asyncio.run(builder.build_user_graph("u1"))

        assert graph.number_of_nodes() == 0
