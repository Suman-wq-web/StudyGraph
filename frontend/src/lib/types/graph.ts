import type { RelationType } from "./edge";

/**
 * Mirrors `GraphNode`/`GraphEdgeResponse`/`GraphResponse` in
 * backend/app/models/graph.py (Phase 6) -- the response shape for
 * GET /api/v1/graph.
 */

export interface GraphNode {
  id: string;
  name: string;
  description: string | null;
  sourceResourceIds: string[];
  centralityScore: number | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relationType: RelationType;
  weight: number;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/** Mirrors `ExtractionTriggerResponse` in backend/app/models/graph.py --
 * response body for POST /resources/{id}/extract. */
export interface ExtractionTriggerResponse {
  resourceId: string;
  chunksPending: number;
}

/** Mirrors `ExtractionStatusResponse` in backend/app/models/graph.py --
 * response body for GET /resources/{id}/extraction-status. */
export interface ExtractionStatusResponse {
  resourceId: string;
  extractedChunkCount: number;
  totalChunkCount: number;
  updatedAt: string;
}
