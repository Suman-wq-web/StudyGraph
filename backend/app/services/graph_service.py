"""
Orchestrates GET /api/v1/graph: build this user's NetworkX graph, compute
centrality, and serialize the result -- app/services/graph/builder.py +
app/services/graph/traversal.py, joined here the same way
embedding_service.py/search_service.py sit above their respective
single-purpose modules.
"""

from app.db import concept_repository
from app.models.graph import GraphEdgeResponse, GraphNode, GraphResponse
from app.services.graph import builder, traversal


async def get_graph(user_id: str) -> GraphResponse:
    graph = await builder.build_user_graph(user_id)
    centrality = traversal.compute_centrality(graph)

    if centrality:
        await concept_repository.set_centrality_scores(centrality)

    nodes = [
        GraphNode(
            id=node_id,
            name=data["name"],
            description=data.get("description"),
            source_resource_ids=data.get("source_resource_ids", []),
            centrality_score=centrality.get(node_id),
        )
        for node_id, data in graph.nodes(data=True)
    ]
    edges = [
        GraphEdgeResponse(
            id=data["id"],
            source=source_id,
            target=target_id,
            relation_type=data["relation_type"],
            weight=data["weight"],
        )
        for source_id, target_id, data in graph.edges(data=True)
    ]
    return GraphResponse(nodes=nodes, edges=edges)
