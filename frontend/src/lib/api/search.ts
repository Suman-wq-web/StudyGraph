import { apiFetch } from "./client";
import type { VectorSearchRequest, VectorSearchResponse } from "@/lib/types/search";

/** Client for `/api/v1/search` on the FastAPI backend. */

export async function vectorSearch(request: VectorSearchRequest): Promise<VectorSearchResponse> {
  return apiFetch<VectorSearchResponse>("/api/v1/search/vector", {
    method: "POST",
    body: JSON.stringify(request),
  });
}
