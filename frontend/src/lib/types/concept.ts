/**
 * Mirrors the `concepts` MongoDB collection (see ARCHITECTURE.md) and the
 * backend `Concept` model (backend/app/models/concept.py). Written by the
 * Phase 6 extraction pipeline (backend/app/services/graph_extraction_service.py).
 */

export interface Concept {
  id: string;
  userId: string;
  name: string;
  description: string | null;
  aliases: string[];
  sourceResourceIds: string[];
  centralityScore: number | null;
}
