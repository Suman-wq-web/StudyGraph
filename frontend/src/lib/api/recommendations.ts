import { apiFetch } from "./client";
import type { RecommendationResponse } from "@/lib/types/recommendation";

/**
 * Client for `/api/v1/recommendations` on the FastAPI backend -- ranked
 * "what to learn next" suggestions, deterministically derived from the
 * knowledge graph on every call (no caching). See
 * backend/app/api/v1/recommendations.py and
 * backend/app/services/recommendation_service.py.
 */
export async function getRecommendations(limit?: number): Promise<RecommendationResponse> {
  const query = typeof limit === "number" ? `?limit=${limit}` : "";
  return apiFetch<RecommendationResponse>(`/api/v1/recommendations${query}`);
}
