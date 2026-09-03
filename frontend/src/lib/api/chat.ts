import { apiFetchStream } from "./client";
import type { ChatQueryRequest, ChatStreamEvent } from "@/lib/types/chat";

/**
 * Client for `POST /api/v1/chat` on the FastAPI backend -- streams a
 * hybrid-retrieval, citation-grounded RAG answer as Server-Sent Events (see
 * docs/API.md, "POST /api/v1/chat"). Pure transport: parses SSE framing
 * (`event:`/`data:` lines, `\n\n`-delimited frames) into typed events. No
 * retrieval/ranking/prompt/citation logic lives here -- that's entirely
 * server-side (app/services/rag/*).
 */
export async function* streamChatQuery(
  request: ChatQueryRequest,
  signal?: AbortSignal
): AsyncGenerator<ChatStreamEvent> {
  const res = await apiFetchStream("/api/v1/chat", {
    method: "POST",
    body: JSON.stringify(request),
    signal,
  });

  const body = res.body;
  if (!body) return;

  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const parsed = parseSseFrame(frame);
        if (parsed) yield parsed;
        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseSseFrame(frame: string): ChatStreamEvent | null {
  let event: string | null = null;
  let data: string | null = null;
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice("event:".length).trim();
    else if (line.startsWith("data:")) data = line.slice("data:".length).trim();
  }
  if (!event || data === null) return null;

  const parsedData = JSON.parse(data);
  switch (event) {
    case "citations":
    case "token":
    case "done":
    case "error":
      return { event, data: parsedData } as ChatStreamEvent;
    default:
      return null;
  }
}
