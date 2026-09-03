"""
Tests for app/services/graph/traversal.py: compute_centrality and
suggest_learning_path over small fixture graphs. No DB, no FastAPI.
"""

import networkx as nx

from app.services.graph import traversal


def _graph_with_prereq_chain() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("basics", name="Basics")
    graph.add_node("calculus", name="Calculus")
    graph.add_node("gradient_descent", name="Gradient Descent")
    graph.add_edge("basics", "calculus", relation_type="prerequisite_of", weight=1.0)
    graph.add_edge("calculus", "gradient_descent", relation_type="prerequisite_of", weight=1.0)
    return graph


class TestComputeCentrality:
    def test_empty_graph_returns_empty_dict(self):
        assert traversal.compute_centrality(nx.DiGraph()) == {}

    def test_betweenness_scores_every_node(self):
        graph = _graph_with_prereq_chain()

        scores = traversal.compute_centrality(graph)

        assert set(scores) == set(graph.nodes)
        # "calculus" sits on the only path between the other two -- highest betweenness.
        assert scores["calculus"] >= scores["basics"]
        assert scores["calculus"] >= scores["gradient_descent"]


class TestSuggestLearningPath:
    def test_missing_target_returns_empty_list(self):
        assert traversal.suggest_learning_path(nx.DiGraph(), "nope") == []

    def test_returns_prerequisites_in_learn_first_order(self):
        graph = _graph_with_prereq_chain()

        path = traversal.suggest_learning_path(graph, "gradient_descent")

        assert path.index("basics") < path.index("calculus") < path.index("gradient_descent")

    def test_unrelated_nodes_are_excluded(self):
        graph = _graph_with_prereq_chain()
        graph.add_node("unrelated", name="Unrelated")

        path = traversal.suggest_learning_path(graph, "gradient_descent")

        assert "unrelated" not in path

    def test_non_prerequisite_edges_are_ignored(self):
        graph = nx.DiGraph()
        graph.add_edge("a", "b", relation_type="related_to", weight=1.0)

        path = traversal.suggest_learning_path(graph, "b")

        assert path == ["b"]

    def test_cycle_falls_back_to_a_complete_ordering(self):
        graph = nx.DiGraph()
        graph.add_edge("a", "b", relation_type="prerequisite_of", weight=1.0)
        graph.add_edge("b", "a", relation_type="prerequisite_of", weight=1.0)

        path = traversal.suggest_learning_path(graph, "a")

        assert set(path) == {"a", "b"}
