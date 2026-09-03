"""
Orchestrates GET /api/v1/recommendations: build this user's NetworkX graph
(app/services/graph/builder.py, unmodified), compute centrality
(app/services/graph/traversal.py, unmodified), run the v1 gap/next-step
heuristics (app/services/graph/recommendations.py), and format each
candidate into a templated, numbers-backed `reason` sentence -- never
model-generated text, no LLM call. Mirrors graph_service.py's shape.
"""

from app.models.recommendation import (
    Recommendation,
    RecommendationReasonType,
    RecommendationResponse,
)
from app.services.graph import builder, recommendations as recommendation_algorithms, traversal

DEFAULT_LIMIT = 10


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _gap_reason(candidate, concept_name: str) -> str:
    return (
        f"{concept_name} is a prerequisite for "
        f"{_plural(candidate.dependent_count, 'other concept')} in your knowledge graph, "
        f"but you only have {_plural(candidate.coverage, 'resource')} covering it -- "
        "worth going deeper here."
    )


def _next_step_reason(candidate, concept_name: str, prerequisite_name: str) -> str:
    return (
        f"You have {_plural(candidate.source_coverage, 'resource')} on {prerequisite_name}, "
        f"which is a prerequisite for {concept_name} "
        f"({_plural(candidate.target_coverage, 'resource')} so far) -- a natural next step."
    )


async def get_recommendations(user_id: str, limit: int = DEFAULT_LIMIT) -> RecommendationResponse:
    """
    Empty `concepts`/`edges` (nothing extracted yet) returns `{"items": []}`,
    not an error -- same contract as GET /api/v1/graph. `limit` splits
    roughly evenly between the two heuristics; a category with fewer
    qualifying candidates than its half never blocks the other from filling
    the rest.
    """
    graph = await builder.build_user_graph(user_id)
    centrality = traversal.compute_centrality(graph)

    gaps = recommendation_algorithms.find_gaps(graph, centrality)
    next_steps = recommendation_algorithms.find_next_steps(graph, centrality)

    # Two-pass, symmetric allocation: give gaps up to half, let next-steps
    # take whatever's left (capped by its own availability), then let gaps
    # reclaim any slots next-steps didn't use -- so a category with fewer
    # qualifying candidates than its half never blocks the other from
    # filling the rest, in either direction.
    gap_take = min(len(gaps), (limit + 1) // 2)
    next_step_take = min(len(next_steps), limit - gap_take)
    gap_take = min(len(gaps), limit - next_step_take)

    items: list[Recommendation] = []

    for candidate in gaps[:gap_take]:
        name = graph.nodes[candidate.concept_id]["name"]
        items.append(
            Recommendation(
                concept_id=candidate.concept_id,
                concept_name=name,
                reason_type=RecommendationReasonType.GAP,
                reason=_gap_reason(candidate, name),
                score=candidate.score,
                related_concept_ids=list(candidate.dependent_concept_ids),
                source_resource_ids=graph.nodes[candidate.concept_id].get(
                    "source_resource_ids", []
                ),
            )
        )

    for candidate in next_steps[:next_step_take]:
        name = graph.nodes[candidate.concept_id]["name"]
        prerequisite_name = graph.nodes[candidate.prerequisite_concept_id]["name"]
        items.append(
            Recommendation(
                concept_id=candidate.concept_id,
                concept_name=name,
                reason_type=RecommendationReasonType.NEXT_STEP,
                reason=_next_step_reason(candidate, name, prerequisite_name),
                score=candidate.score,
                related_concept_ids=[candidate.prerequisite_concept_id],
                source_resource_ids=graph.nodes[candidate.concept_id].get(
                    "source_resource_ids", []
                ),
            )
        )

    return RecommendationResponse(items=items)
