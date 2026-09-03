import type { ResourceType } from "@/lib/types/resource";

/**
 * RAG chat shapes (Phase 5). Mirrors `backend/app/models/chat.py` --
 * `Citation`/`ChatQueryRequest`/`Chat*EventData` are camelCase on the wire
 * via Pydantic's `alias_generator=to_camel`. See docs/API.md
 * ("POST /api/v1/chat") for the exact SSE event sequence.
 */

export interface Citation {
  resourceId: string;
  resourceTitle: string;
  resourceType: ResourceType;
  chunkId: string;
  chunkIndex: number;
  /** Truncated preview (RAG_MAX_SNIPPET_CHARS chars) -- the full chunk text is what's in the prompt. */
  snippet: string;
  /** Fused reciprocal-rank-fusion score -- unbounded, not a [0,1] similarity. */
  score: number;
}

export interface ChatQueryRequest {
  query: string;
  topK?: number;
  resourceType?: ResourceType;
  tags?: string[];
}

/** One line of `POST /api/v1/chat`'s SSE body, after framing is parsed. */
export type ChatStreamEvent =
  | { event: "citations"; data: { citations: Citation[] } }
  | { event: "token"; data: { delta: string } }
  | { event: "done"; data: { finishReason: string | null } }
  | { event: "error"; data: { message: string } };

export type ChatMessageStatus = "streaming" | "done" | "error";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  /** Only meaningful for role "assistant". */
  status?: ChatMessageStatus;
  errorMessage?: string;
}
