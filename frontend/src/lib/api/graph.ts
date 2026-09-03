import { apiFetch } from "./client";
import type { GraphResponse } from "@/lib/types/graph";

/**
 * Client for `/api/v1/graph` on the FastAPI backend -- nodes/edges for
 * react-force-graph, rebuilt (with fresh centrality) on every call. See
 * backend/app/api/v1/graph.py and backend/app/services/graph_service.py.
 */
export async function getKnowledgeGraph(): Promise<GraphResponse> {
  return apiFetch<GraphResponse>("/api/v1/graph");
}
