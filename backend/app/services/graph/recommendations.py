"""
Pure, deterministic v1 "what to learn next" heuristics over the NetworkX
graph built in builder.py and the centrality scores computed by
traversal.py -- no LLM calls, no mastery/completion data (none exists in
the schema). "Coverage" is approximated by how many resources a concept
was extracted from (`source_resource_ids`), a field builder.py already
attaches to every node -- see docs/KNOWLEDGE_GRAPH.md ("Phase 7") and
docs/ROADMAP.md. Reads the graph only; never mutates it or touches Mongo.
"""

from dataclasses import dataclass

import networkx as nx


@dataclass(frozen=True)
class GapCandidate:
    """A concept many other concepts structurally depend on (high
    out-degree in the `prerequisite_of` subgraph -- many things list it as
    their prerequisite) but that is shallowly covered relative to that
    importance."""

    concept_id: str
    dependent_concept_ids: tuple[str, ...]
    coverage: int
    score: float

    @property
    def dependent_count(self) -> int:
        return len(self.dependent_concept_ids)


@dataclass(frozen=True)
class NextStepCandidate:
    """A concept reachable via one `prerequisite_of` hop from a concept the
    user already covers well, that is itself shallower than that
    prerequisite -- "you know X well; X is a prerequisite of Y; Y is
    shallow; learn Y next"."""

    concept_id: str
    prerequisite_concept_id: str
    source_coverage: int
    target_coverage: int
    score: float


def _coverage(graph: nx.DiGraph, node_id: str) -> int:
    return len(graph.nodes[node_id].get("source_resource_ids", []))


def _prerequisite_subgraph(graph: nx.DiGraph) -> nx.DiGraph:
    """Restricts `graph` to `prerequisite_of` edges only, same construction
    as traversal.py:suggest_learning_path -- kept local (not imported from
    traversal.py) so this module stays a self-contained, independently
    testable unit with no dependency beyond networkx."""
    prereq_graph = nx.DiGraph()
    prereq_graph.add_nodes_from(graph.nodes)
    for source, target, data in graph.edges(data=True):
        if data.get("relation_type") == "prerequisite_of":
            prereq_graph.add_edge(source, target)
    return prereq_graph


def find_gaps(
    graph: nx.DiGraph,
    centrality: dict[str, float],
    limit: int | None = None,
) -> list[GapCandidate]:
    """
    Ranks concepts by `out_degree * (1 + betweenness_centrality) / coverage`
    -- structurally load-bearing concepts (many dependents, high
    centrality) that have few source resources behind them. A concept with
    no dependents (out-degree 0 in the prerequisite_of subgraph) is never a
    gap, regardless of coverage -- nothing depends on it. Deterministic:
    ties broken by `concept_id` so ordering never depends on dict/graph
    iteration order.
    """
    prereq_graph = _prerequisite_subgraph(graph)
    candidates: list[GapCandidate] = []
    for node_id in graph.nodes:
        dependent_ids = tuple(sorted(prereq_graph.successors(node_id)))
        if not dependent_ids:
            continue
        coverage = _coverage(graph, node_id)
        if coverage == 0:
            continue
        score = len(dependent_ids) * (1 + centrality.get(node_id, 0.0)) / coverage
        candidates.append(GapCandidate(node_id, dependent_ids, coverage, score))

    candidates.sort(key=lambda c: (-c.score, c.concept_id))
    return candidates[:limit] if limit is not None else candidates


def find_next_steps(
    graph: nx.DiGraph,
    centrality: dict[str, float],
    limit: int | None = None,
) -> list[NextStepCandidate]:
    """
    For every `prerequisite_of` edge (source -> target) where the source is
    better-covered than the target, scores the target as a next-step
    candidate: `((source_coverage - target_coverage) / source_coverage) *
    (1 + source_centrality)`. A target reachable from multiple
    well-covered prerequisites keeps only its best-scoring one (highest
    score, ties broken by `prerequisite_concept_id`) rather than appearing
    once per qualifying source. Deterministic: final ordering ties broken
    by `concept_id`.
    """
    prereq_graph = _prerequisite_subgraph(graph)
    coverage = {node_id: _coverage(graph, node_id) for node_id in graph.nodes}

    best_by_target: dict[str, NextStepCandidate] = {}
    for source, target in prereq_graph.edges:
        source_coverage = coverage[source]
        target_coverage = coverage[target]
        if source_coverage <= target_coverage or source_coverage == 0:
            continue

        score = (
            (source_coverage - target_coverage)
            / source_coverage
            * (1 + centrality.get(source, 0.0))
        )
        candidate = NextStepCandidate(target, source, source_coverage, target_coverage, score)

        existing = best_by_target.get(target)
        is_better = existing is None or (
            candidate.score > existing.score
            or (
                candidate.score == existing.score
                and candidate.prerequisite_concept_id < existing.prerequisite_concept_id
            )
        )
        if is_better:
            best_by_target[target] = candidate

    candidates = sorted(best_by_target.values(), key=lambda c: (-c.score, c.concept_id))
    return candidates[:limit] if limit is not None else candidates
