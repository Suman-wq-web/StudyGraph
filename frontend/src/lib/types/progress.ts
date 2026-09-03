/** Mirrors the Pydantic models in `backend/app/models/progress.py`. */

import type { ResourceType } from "@/lib/types/resource";

export type ProgressStatus = "not_started" | "in_progress" | "completed";

/** `id`/`createdAt`/`updatedAt` are `null` when a resource has no progress
 * activity yet -- GET /resources/{id}/progress returns a synthesized
 * `not_started` default rather than 404ing for that case. */
export interface ResourceProgress {
  id: string | null;
  userId: string;
  resourceId: string;
  status: ProgressStatus;
  progressPercent: number;
  positionSeconds: number | null;
  durationSeconds: number | null;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface ProgressUpdateInput {
  status?: ProgressStatus;
  progressPercent?: number;
  positionSeconds?: number;
  durationSeconds?: number;
}

/** One row of GET /resources/progress/in-progress -- resource metadata
 * flattened together with its progress. */
export interface InProgressResource {
  resourceId: string;
  title: string;
  type: ResourceType;
  status: ProgressStatus;
  progressPercent: number;
  positionSeconds: number | null;
  durationSeconds: number | null;
  updatedAt: string;
}

export interface InProgressResourcesResponse {
  items: InProgressResource[];
}

/** Mirrors COMPLETION_THRESHOLD_PERCENT in backend/app/models/progress.py --
 * used client-side only to decide when to stop polling/show a "completed"
 * hint before the next save round-trips; the server is the source of truth
 * for the actual status. */
export const COMPLETION_THRESHOLD_PERCENT = 95;
