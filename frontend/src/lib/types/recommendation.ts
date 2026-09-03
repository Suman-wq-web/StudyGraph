/**
 * Mirrors `Recommendation`/`RecommendationResponse` in
 * backend/app/models/recommendation.py (Phase 7) -- the response shape for
 * GET /api/v1/recommendations. Deterministically derived from the existing
 * knowledge graph (centrality, source coverage, `prerequisite_of`
 * structure); `reason` is a templated sentence, not model-generated text.
 */

export type RecommendationReasonType = "gap" | "next_step";

export interface Recommendation {
  conceptId: string;
  conceptName: string;
  reasonType: RecommendationReasonType;
  reason: string;
  score: number;
  relatedConceptIds: string[];
  sourceResourceIds: string[];
}

export interface RecommendationResponse {
  items: Recommendation[];
}
