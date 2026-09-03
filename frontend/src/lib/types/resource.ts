/** Mirrors the Pydantic models in `backend/app/models/resource.py`. */

export type ResourceType = "article" | "video" | "url" | "note";

export type ResourceStatus = "pending" | "processing" | "ready" | "embedding" | "embedded" | "failed";

export interface Resource {
  id: string;
  title: string;
  description: string | null;
  type: ResourceType;
  sourceUrl: string | null;
  content: string | null;
  tags: string[];
  status: ResourceStatus;
  processingError: string | null;
  createdAt: string;
  updatedAt: string;
}

/** Mirrors `ProcessingStatusResponse` in `backend/app/models/processing.py`. */
export interface ProcessingStatusResponse {
  resourceId: string;
  status: ResourceStatus;
  chunkCount: number;
  processingError: string | null;
  updatedAt: string;
}

/** Mirrors `EmbeddingStatusResponse` in `backend/app/models/embedding.py`. */
export interface EmbeddingStatusResponse {
  resourceId: string;
  status: ResourceStatus;
  embeddedChunkCount: number;
  totalChunkCount: number;
  processingError: string | null;
  updatedAt: string;
}

export interface ResourceListResponse {
  items: Resource[];
  total: number;
  skip: number;
  limit: number;
}

export interface ResourceStats {
  total: number;
  byType: Record<string, number>;
  byStatus: Record<string, number>;
}

export interface ResourceCreateInput {
  title: string;
  description?: string | null;
  type: ResourceType;
  sourceUrl?: string | null;
  content?: string | null;
  tags?: string[];
}

export interface ResourceUpdateInput {
  title?: string;
  description?: string | null;
  type?: ResourceType;
  sourceUrl?: string | null;
  content?: string | null;
  tags?: string[];
}

export const RESOURCE_TYPES: ResourceType[] = ["article", "url", "video", "note"];

export const RESOURCE_TYPE_LABELS: Record<ResourceType, string> = {
  article: "Article",
  url: "URL",
  video: "Video",
  note: "Note",
};
