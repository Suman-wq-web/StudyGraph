"""
Tests for app/services/graph/recommendations.py: find_gaps and
find_next_steps over small fixture graphs. No DB, no FastAPI -- mirrors
test_graph_traversal.py's style.
"""

import networkx as nx

from app.services.graph import recommendations


def _node(graph: nx.DiGraph, node_id: str, *, name: str, source_resource_ids: list[str]) -> None:
    graph.add_node(node_id, name=name, source_resource_ids=source_resource_ids)


class TestFindGaps:
    def test_empty_graph_returns_no_gaps(self):
        assert recommendations.find_gaps(nx.DiGraph(), {}) == []

    def test_concept_with_no_dependents_is_never_a_gap(self):
        graph = nx.DiGraph()
        _node(graph, "isolated", name="Isolated", source_resource_ids=["r1"])

        assert recommendations.find_gaps(graph, {}) == []

    def test_shallow_high_fanout_concept_ranks_above_well_covered_one(self):
        graph = nx.DiGraph()
        _node(graph, "shallow_hub", name="Shallow Hub", source_resource_ids=["r1"])
        _node(graph, "deep_hub", name="Deep Hub", source_resource_ids=["r1", "r2", "r3"])
        _node(graph, "a", name="A", source_resource_ids=["r1"])
        _node(graph, "b", name="B", source_resource_ids=["r1"])
        graph.add_edge("shallow_hub", "a", relation_type="prerequisite_of", weight=1.0)
        graph.add_edge("shallow_hub", "b", relation_type="prerequisite_of", weight=1.0)
        graph.add_edge("deep_hub", "a", relation_type="prerequisite_of", weight=1.0)
        graph.add_edge("deep_hub", "b", relation_type="prerequisite_of", weight=1.0)

        gaps = recommendations.find_gaps(graph, {})

        gap_ids = [g.concept_id for g in gaps]
        assert gap_ids.index("shallow_hub") < gap_ids.index("deep_hub")

    def test_higher_centrality_increases_score(self):
        graph = nx.DiGraph()
        _node(graph, "x", name="X", source_resource_ids=["r1"])
        _node(graph, "y", name="Y", source_resource_ids=["r1"])
        graph.add_edge("x", "y", relation_type="prerequisite_of", weight=1.0)

        low = recommendations.find_gaps(graph, {"x": 0.0})[0]
        high = recommendations.find_gaps(graph, {"x": 1.0})[0]

        assert high.score > low.score

    def test_non_prerequisite_edges_do_not_count_as_dependents(self):
        graph = nx.DiGraph()
        _node(graph, "x", name="X", source_resource_ids=["r1"])
        _node(graph, "y", name="Y", source_resource_ids=["r1"])
        graph.add_edge("x", "y", relation_type="related_to", weight=1.0)

        assert recommendations.find_gaps(graph, {}) == []

    def test_dependent_concept_ids_are_sorted_and_deduplicated_via_graph_structure(self):
        graph = nx.DiGraph()
        _node(graph, "x", name="X", source_resource_ids=["r1"])
        _node(graph, "b", name="B", source_resource_ids=["r1"])
        _node(graph, "a", name="A", source_resource_ids=["r1"])
        graph.add_edge("x", "b", relation_type="prerequisite_of", weight=1.0)
        graph.add_edge("x", "a", relation_type="prerequisite_of", weight=1.0)

        gaps = recommendations.find_gaps(graph, {})

        assert gaps[0].dependent_concept_ids == ("a", "b")

    def test_limit_truncates_results(self):
        graph = nx.DiGraph()
        for i in range(5):
            _node(graph, f"hub{i}", name=f"Hub {i}", source_resource_ids=["r1"])
            _node(graph, f"leaf{i}", name=f"Leaf {i}", source_resource_ids=["r1"])
            graph.add_edge(f"hub{i}", f"leaf{i}", relation_type="prerequisite_of", weight=1.0)

        assert len(recommendations.find_gaps(graph, {}, limit=2)) == 2

    def test_deterministic_ordering_breaks_ties_by_concept_id(self):
        graph = nx.DiGraph()
        for cid in ("z", "y", "x"):
            _node(graph, cid, name=cid.upper(), source_resource_ids=["r1"])
            leaf = f"{cid}_leaf"
            _node(graph, leaf, name=leaf, source_resource_ids=["r1"])
            graph.add_edge(cid, leaf, relation_type="prerequisite_of", weight=1.0)

        gaps = recommendations.find_gaps(graph, {})

        hub_ids = [g.concept_id for g in gaps if g.concept_id in {"x", "y", "z"}]
        assert hub_ids == ["x", "y", "z"]


class TestFindNextSteps:
    def test_empty_graph_returns_no_next_steps(self):
        assert recommendations.find_next_steps(nx.DiGraph(), {}) == []

    def test_shallower_source_than_target_is_excluded(self):
        graph = nx.DiGraph()
        _node(graph, "shallow", name="Shallow", source_resource_ids=["r1"])
        _node(graph, "deep", name="Deep", source_resource_ids=["r1", "r2"])
        graph.add_edge("shallow", "deep", relation_type="prerequisite_of", weight=1.0)

        assert recommendations.find_next_steps(graph, {}) == []

    def test_well_covered_source_recommends_shallow_target(self):
        graph = nx.DiGraph()
        _node(graph, "known", name="Known", source_resource_ids=["r1", "r2", "r3"])
        _node(graph, "next", name="Next", source_resource_ids=["r1"])
        graph.add_edge("known", "next", relation_type="prerequisite_of", weight=1.0)

        steps = recommendations.find_next_steps(graph, {})

        assert len(steps) == 1
        assert steps[0].concept_id == "next"
        assert steps[0].prerequisite_concept_id == "known"

    def test_target_with_multiple_qualifying_sources_keeps_only_best(self):
        graph = nx.DiGraph()
        _node(graph, "weak_source", name="Weak Source", source_resource_ids=["r1", "r2"])
        _node(graph, "strong_source", name="Strong Source", source_resource_ids=["r1", "r2", "r3", "r4"])
        _node(graph, "target", name="Target", source_resource_ids=["r1"])
        graph.add_edge("weak_source", "target", relation_type="prerequisite_of", weight=1.0)
        graph.add_edge("strong_source", "target", relation_type="prerequisite_of", weight=1.0)

        steps = recommendations.find_next_steps(graph, {})

        assert len(steps) == 1
        assert steps[0].prerequisite_concept_id == "strong_source"

    def test_non_prerequisite_edges_are_ignored(self):
        graph = nx.DiGraph()
        _node(graph, "known", name="Known", source_resource_ids=["r1", "r2"])
        _node(graph, "other", name="Other", source_resource_ids=["r1"])
        graph.add_edge("known", "other", relation_type="related_to", weight=1.0)

        assert recommendations.find_next_steps(graph, {}) == []

    def test_limit_truncates_results(self):
        graph = nx.DiGraph()
        for i in range(5):
            _node(graph, f"known{i}", name=f"Known {i}", source_resource_ids=["r1", "r2"])
            _node(graph, f"next{i}", name=f"Next {i}", source_resource_ids=["r1"])
            graph.add_edge(f"known{i}", f"next{i}", relation_type="prerequisite_of", weight=1.0)

        assert len(recommendations.find_next_steps(graph, {}, limit=2)) == 2
