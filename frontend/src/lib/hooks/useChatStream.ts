"use client";

import { useCallback, useRef, useState } from "react";
import { streamChatQuery } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/client";
import type { ChatMessage, ChatQueryRequest } from "@/lib/types/chat";

export type ChatStatus = "idle" | "streaming" | "error";

let nextId = 0;
function newId(prefix: string) {
  return `${prefix}-${Date.now()}-${nextId++}`;
}

/**
 * Owns the visible chat transcript and drives POST /api/v1/chat's SSE
 * stream (see lib/api/chat.ts). The backend is stateless per request --
 * `ChatQueryRequest` has no conversation/session field, so each
 * sendMessage() is an independent RAG query. This hook keeps the multi-turn
 * *display* on the client only; it never sends prior turns back as context,
 * matching what the backend actually supports today.
 */
export function useChatStream() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ChatStatus>("idle");
  const abortRef = useRef<AbortController | null>(null);
  const lastQueryRef = useRef<string | null>(null);

  const run = useCallback(async (query: string) => {
    const controller = new AbortController();
    abortRef.current = controller;
    lastQueryRef.current = query;

    const assistantId = newId("assistant");
    setMessages((prev) => [
      ...prev,
      { id: newId("user"), role: "user", content: query, citations: [] },
      { id: assistantId, role: "assistant", content: "", citations: [], status: "streaming" },
    ]);
    setStatus("streaming");

    const patchAssistant = (patch: Partial<ChatMessage>) => {
      setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, ...patch } : m)));
    };

    try {
      const request: ChatQueryRequest = { query };
      for await (const event of streamChatQuery(request, controller.signal)) {
        switch (event.event) {
          case "citations":
            patchAssistant({ citations: event.data.citations });
            break;
          case "token":
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, content: m.content + event.data.delta } : m
              )
            );
            break;
          case "done":
            patchAssistant({ status: "done" });
            setStatus("idle");
            break;
          case "error":
            patchAssistant({ status: "error", errorMessage: event.data.message });
            setStatus("error");
            break;
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        patchAssistant({ status: "done" });
        setStatus("idle");
        return;
      }
      const message =
        err instanceof ApiError
          ? err.message
          : "Could not reach the StudyGraph API. Is the backend running?";
      patchAssistant({ status: "error", errorMessage: message });
      setStatus("error");
    } finally {
      abortRef.current = null;
    }
  }, []);

  const sendMessage = useCallback(
    (query: string) => {
      const trimmed = query.trim();
      if (!trimmed || status === "streaming") return;
      run(trimmed);
    },
    [run, status]
  );

  const retry = useCallback(() => {
    if (!lastQueryRef.current || status === "streaming") return;
    const query = lastQueryRef.current;
    // Drop the failed user+assistant pair before re-running, so retrying
    // doesn't leave a duplicate question in the transcript.
    setMessages((prev) => {
      const lastUserIndex = prev.map((m) => m.role).lastIndexOf("user");
      return lastUserIndex === -1 ? prev : prev.slice(0, lastUserIndex);
    });
    run(query);
  }, [run, status]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { messages, status, sendMessage, retry, stop };
}
