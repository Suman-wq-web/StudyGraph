import { apiFetch } from "./client";
import type {
  EmbeddingStatusResponse,
  ProcessingStatusResponse,
  Resource,
  ResourceCreateInput,
  ResourceListResponse,
  ResourceStats,
  ResourceType,
  ResourceUpdateInput,
} from "@/lib/types/resource";
import type { ExtractionStatusResponse, ExtractionTriggerResponse } from "@/lib/types/graph";

/** Client for `/api/v1/resources` on the FastAPI backend. */

export interface ListResourcesParams {
  type?: ResourceType;
  tag?: string;
  search?: string;
  skip?: number;
  limit?: number;
}

function buildQueryString(params: ListResourcesParams): string {
  const query = new URLSearchParams();
  if (params.type) query.set("type", params.type);
  if (params.tag) query.set("tag", params.tag);
  if (params.search) query.set("search", params.search);
  if (params.skip !== undefined) query.set("skip", String(params.skip));
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  const qs = query.toString();
  return qs ? `?${qs}` : "";
}

export async function listResources(
  params: ListResourcesParams = {}
): Promise<ResourceListResponse> {
  return apiFetch<ResourceListResponse>(`/api/v1/resources${buildQueryString(params)}`);
}

export async function getResource(id: string): Promise<Resource> {
  return apiFetch<Resource>(`/api/v1/resources/${id}`);
}

export async function createResource(payload: ResourceCreateInput): Promise<Resource> {
  return apiFetch<Resource>("/api/v1/resources", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateResource(
  id: string,
  payload: ResourceUpdateInput
): Promise<Resource> {
  return apiFetch<Resource>(`/api/v1/resources/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteResource(id: string): Promise<void> {
  await apiFetch<void>(`/api/v1/resources/${id}`, { method: "DELETE" });
}

export async function getResourceStats(): Promise<ResourceStats> {
  return apiFetch<ResourceStats>("/api/v1/resources/stats");
}

/** Starts (or restarts) the document-processing pipeline. Resolves as soon as the
 * resource flips to "processing" -- the pipeline itself finishes in the background. */
export async function processResource(id: string): Promise<Resource> {
  return apiFetch<Resource>(`/api/v1/resources/${id}/process`, { method: "POST" });
}

export async function getProcessingStatus(id: string): Promise<ProcessingStatusResponse> {
  return apiFetch<ProcessingStatusResponse>(`/api/v1/resources/${id}/processing-status`);
}

/** Starts (or restarts) embedding a chunked resource's chunks. Requires the
 * resource to already be processed (chunked) -- see processResource(). */
export async function embedResource(id: string): Promise<Resource> {
  return apiFetch<Resource>(`/api/v1/resources/${id}/embed`, { method: "POST" });
}

export async function getEmbeddingStatus(id: string): Promise<EmbeddingStatusResponse> {
  return apiFetch<EmbeddingStatusResponse>(`/api/v1/resources/${id}/embedding-status`);
}

/** Starts (or restarts) concept/relationship extraction for a chunked
 * resource's chunks (Phase 6). Requires the resource to already be
 * processed (chunked) -- see processResource(). Unlike processResource/
 * embedResource, this doesn't return the Resource itself -- there's no
 * status field it changes; poll getExtractionStatus() for progress. */
export async function extractResource(id: string): Promise<ExtractionTriggerResponse> {
  return apiFetch<ExtractionTriggerResponse>(`/api/v1/resources/${id}/extract`, { method: "POST" });
}

export async function getExtractionStatus(id: string): Promise<ExtractionStatusResponse> {
  return apiFetch<ExtractionStatusResponse>(`/api/v1/resources/${id}/extraction-status`);
}
