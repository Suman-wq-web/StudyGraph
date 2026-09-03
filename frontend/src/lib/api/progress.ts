import { apiFetch } from "./client";
import type {
  InProgressResourcesResponse,
  ProgressUpdateInput,
  ResourceProgress,
} from "@/lib/types/progress";

/** Client for the resource progress endpoints on the FastAPI backend
 * (GET/PATCH /api/v1/resources/{id}/progress, POST .../complete,
 * GET /api/v1/resources/progress/in-progress). */

export async function getProgress(resourceId: string): Promise<ResourceProgress> {
  return apiFetch<ResourceProgress>(`/api/v1/resources/${resourceId}/progress`);
}

/** Saves reading/watch progress. Callers should throttle how often they call
 * this (see lib/hooks/useResourceProgress.ts) rather than firing it on
 * every tiny playback/scroll event. */
export async function updateProgress(
  resourceId: string,
  payload: ProgressUpdateInput
): Promise<ResourceProgress> {
  return apiFetch<ResourceProgress>(`/api/v1/resources/${resourceId}/progress`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function completeProgress(resourceId: string): Promise<ResourceProgress> {
  return apiFetch<ResourceProgress>(`/api/v1/resources/${resourceId}/progress/complete`, {
    method: "POST",
  });
}

export async function listInProgressResources(limit = 5): Promise<InProgressResourcesResponse> {
  return apiFetch<InProgressResourcesResponse>(
    `/api/v1/resources/progress/in-progress?limit=${limit}`
  );
}
