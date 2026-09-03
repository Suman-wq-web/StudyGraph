/**
 * Mirrors the `edges` MongoDB collection (see ARCHITECTURE.md).
 * Placeholder shape for Phase 1 -- not yet wired to a real API response.
 */

export type RelationType = "prerequisite_of" | "related_to" | "part_of";

export interface ConceptEdge {
  id: string;
  userId: string;
  sourceConceptId: string;
  targetConceptId: string;
  relationType: RelationType;
  weight: number;
}
