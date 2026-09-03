"""
Builds an in-memory NetworkX DiGraph for one user from the `concepts` and
`edges` collections -- concepts become nodes, edges become directed edges
carrying `relation_type` and `weight`. The resulting graph feeds
traversal.py (centrality, learning paths) and the /api/v1/graph endpoint
that serves react-force-graph. Rebuilt fresh on every call rather than kept
resident, since it's derived data -- see docs/KNOWLEDGE_GRAPH.md.
"""

import networkx as nx

from app.db import concept_repository, edge_repository


async def build_user_graph(user_id: str) -> nx.DiGraph:
    concepts = await concept_repository.list_by_user(user_id)
    edges = await edge_repository.list_by_user(user_id)

    graph = nx.DiGraph()
    for concept in concepts:
        graph.add_node(
            concept.id,
            name=concept.name,
            description=concept.description,
            source_resource_ids=concept.source_resource_ids,
        )

    for edge in edges:
        # Guards against a dangling reference (e.g. a concept deleted after
        # the edge was written -- no cascade delete exists yet) rather than
        # letting NetworkX silently add a node with no attributes for it.
        if edge.source_concept_id in graph and edge.target_concept_id in graph:
            graph.add_edge(
                edge.source_concept_id,
                edge.target_concept_id,
                id=edge.id,
                relation_type=edge.relation_type.value,
                weight=edge.weight,
            )

    return graph
