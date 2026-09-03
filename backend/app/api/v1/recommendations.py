"""'What to learn next' recommendation endpoints, driven by graph analysis (Phase 7)."""

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user_id
from app.models.recommendation import RecommendationResponse
from app.services import recommendation_service

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("", response_model=RecommendationResponse)
async def get_recommendations(
    limit: int = Query(default=recommendation_service.DEFAULT_LIMIT, ge=1, le=50),
    current_user_id: str = Depends(get_current_user_id),
) -> RecommendationResponse:
    """
    Deterministically ranks "gap" (structurally load-bearing but shallowly
    covered) and "next step" (one `prerequisite_of` hop from something
    already well covered) concepts from this user's knowledge graph -- see
    app/services/graph/recommendations.py. No LLM call. Empty
    `concepts`/`edges` (nothing extracted yet) returns `{"items": []}`, not
    an error.
    """
    return await recommendation_service.get_recommendations(current_user_id, limit=limit)
