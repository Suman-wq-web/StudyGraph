/** Mirrors the Pydantic models in `backend/app/models/embedding.py`. */

import type { ResourceType } from "@/lib/types/resource";

export interface VectorSearchRequest {
  query: string;
  topK?: number;
  resourceType?: ResourceType;
  tags?: string[];
}

export interface VectorSearchResultItem {
  chunkId: string;
  resourceId: string;
  resourceTitle: string;
  resourceType: ResourceType;
  chunkIndex: number;
  text: string;
  score: number;
}

export interface VectorSearchResponse {
  query: string;
  results: VectorSearchResultItem[];
  count: number;
}
