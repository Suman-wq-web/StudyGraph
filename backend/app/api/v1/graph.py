"""Knowledge graph endpoints (nodes/edges for visualization, centrality) -- Phase 6."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user_id
from app.models.graph import GraphResponse
from app.services import graph_service

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("", response_model=GraphResponse)
async def get_graph(current_user_id: str = Depends(get_current_user_id)) -> GraphResponse:
    """
    Rebuilds this user's knowledge graph from `concepts`/`edges` on every
    call (see app/services/graph/builder.py), computes centrality, and
    returns {nodes, edges} for react-force-graph. Empty `concepts`/`edges`
    (no resource has been extracted yet) returns an empty graph, not an
    error.
    """
    return await graph_service.get_graph(current_user_id)
