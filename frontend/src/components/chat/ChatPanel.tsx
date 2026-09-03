"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Textarea";
import { EmptyState } from "@/components/ui/EmptyState";
import { CitationBadge } from "@/components/chat/CitationBadge";
import {
  IconAlertTriangle,
  IconChat,
  IconSend,
  IconSparkles,
  IconSpinner,
  IconUser,
} from "@/components/ui/icons";
import { useChatStream } from "@/lib/hooks/useChatStream";
import { cn } from "@/lib/utils/cn";

const MAX_QUERY_LENGTH = 2000;
const TEXTAREA_MAX_HEIGHT_PX = 160;

/**
 * RAG chat interface (Phase 5): streams a citation-grounded answer from
 * `POST /api/v1/chat` via `useChatStream`. All retrieval/generation logic
 * lives server-side (backend/app/services/rag/*) -- this component only
 * renders the transcript and drives the request.
 */
export function ChatPanel() {
  const { messages, status, sendMessage, retry, stop } = useChatStream();
  const [input, setInput] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "auto" });
  }, [messages]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, TEXTAREA_MAX_HEIGHT_PX)}px`;
  }, [input]);

  function submitQuery() {
    if (!input.trim() || status === "streaming") return;
    sendMessage(input);
    setInput("");
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    submitQuery();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitQuery();
    }
  }

  return (
    <div className="flex h-full flex-col gap-4 rounded-2xl border border-base-border bg-base-surface/60 p-4">
      <div ref={listRef} className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <EmptyState
              icon={<IconChat className="h-5 w-5" />}
              title="Ask questions about what you've learned"
              description="Get answers grounded in your saved resources, with citations linking back to the source."
            />
          </div>
        ) : (
          <ul className="flex flex-col gap-4 py-1">
            {messages.map((message) => (
              <li
                key={message.id}
                className={cn("flex gap-2.5", message.role === "user" && "flex-row-reverse")}
              >
                <div
                  className={cn(
                    "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
                    message.role === "user"
                      ? "bg-accent-indigo/10 text-accent-indigo"
                      : "bg-accent-teal/10 text-accent-teal"
                  )}
                >
                  {message.role === "user" ? (
                    <IconUser className="h-3.5 w-3.5" />
                  ) : (
                    <IconSparkles className="h-3.5 w-3.5" />
                  )}
                </div>

                <div
                  className={cn(
                    "flex max-w-[85%] flex-col gap-1.5 sm:max-w-[75%]",
                    message.role === "user" && "items-end"
                  )}
                >
                  {(message.content || message.status === "streaming") && (
                    <div
                      className={cn(
                        "rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
                        message.role === "user"
                          ? "bg-accent-indigo text-white"
                          : "border border-base-border bg-base-elevated text-content-primary"
                      )}
                    >
                      {message.content ? (
                        <p className="whitespace-pre-wrap">{message.content}</p>
                      ) : (
                        <span className="flex items-center gap-1.5 text-content-muted">
                          <IconSpinner className="h-3.5 w-3.5" />
                          Thinking...
                        </span>
                      )}
                    </div>
                  )}

                  {message.citations.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {message.citations.map((citation) => (
                        <CitationBadge key={citation.chunkId} citation={citation} />
                      ))}
                    </div>
                  )}

                  {message.status === "error" && (
                    <div className="flex items-center gap-2 rounded-xl border border-danger/20 bg-danger/5 px-3 py-2 text-xs text-danger">
                      <IconAlertTriangle className="h-3.5 w-3.5 shrink-0" />
                      <span className="flex-1">
                        {message.errorMessage ?? "Something went wrong."}
                      </span>
                      <Button variant="secondary" size="sm" onClick={retry}>
                        Retry
                      </Button>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <form onSubmit={handleSubmit} className="flex shrink-0 items-end gap-2">
        <div className="flex-1">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value.slice(0, MAX_QUERY_LENGTH))}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your saved resources..."
            rows={1}
            disabled={status === "streaming"}
            className="min-h-[42px]"
          />
        </div>
        {status === "streaming" ? (
          <Button type="button" variant="secondary" onClick={stop}>
            Stop
          </Button>
        ) : (
          <Button type="submit" disabled={!input.trim()}>
            <IconSend className="h-4 w-4" />
            Send
          </Button>
        )}
      </form>
    </div>
  );
}
