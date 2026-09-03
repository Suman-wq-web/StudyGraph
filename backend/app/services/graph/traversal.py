"""
Graph analysis over the NetworkX graph built in builder.py: centrality
measures to surface the most "load-bearing" concepts, and traversal over
`prerequisite_of` edges to build ordered learning paths and surface gaps
(concepts referenced as prerequisites but not yet covered) -- the basis for
Phase 7's recommendations. See docs/KNOWLEDGE_GRAPH.md.
"""

import networkx as nx


def compute_centrality(graph: nx.DiGraph) -> dict[str, float]:
    """
    Betweenness centrality: identifies concepts that sit on the most
    shortest paths between other concepts, i.e. structurally load-bearing
    ones. NetworkX's `pagerank` was considered as a configurable
    alternative, but its only implementation requires numpy/scipy (dropped
    the pure-Python fallback), which would add a dependency nothing else in
    this codebase needs -- betweenness alone matches
    requirements.txt (`networkx` only) exactly. Returns {} for an empty
    graph rather than letting NetworkX raise.
    """
    if graph.number_of_nodes() == 0:
        return {}
    return nx.betweenness_centrality(graph, weight="weight")


def suggest_learning_path(graph: nx.DiGraph, target_concept_id: str) -> list[str]:
    """
    Concept ids in learn-first-to-last order, restricted to `target_concept_id`
    and everything reachable to it via `prerequisite_of` edges (an edge
    source -> target means "source is a prerequisite of target"). Returns
    [] if the target isn't in the graph at all. Falls back to a non-
    topological (but still complete) ordering if the prerequisite subgraph
    has a cycle -- extraction has no cycle-prevention today, so this stays
    correct rather than raising on real, if messy, extracted data.
    """
    if target_concept_id not in graph:
        return []

    prereq_graph = nx.DiGraph()
    prereq_graph.add_nodes_from(graph.nodes)
    for source, target, data in graph.edges(data=True):
        if data.get("relation_type") == "prerequisite_of":
            prereq_graph.add_edge(source, target)

    ancestors = nx.ancestors(prereq_graph, target_concept_id)
    relevant_nodes = ancestors | {target_concept_id}
    subgraph = prereq_graph.subgraph(relevant_nodes)

    try:
        return list(nx.topological_sort(subgraph))
    except nx.NetworkXUnfeasible:
        return [*sorted(ancestors), target_concept_id]
