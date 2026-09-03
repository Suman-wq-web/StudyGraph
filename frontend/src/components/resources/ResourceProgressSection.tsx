"use client";

import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { IconCheckCircle, IconClock } from "@/components/ui/icons";
import { useResourceProgress } from "@/lib/hooks/useResourceProgress";
import type { ProgressStatus } from "@/lib/types/progress";
import type { Resource } from "@/lib/types/resource";
import { VideoProgressPlayer } from "@/components/resources/VideoProgressPlayer";
import { ApiError } from "@/lib/api/client";

const STATUS_LABELS: Record<ProgressStatus, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  completed: "Completed",
};

const STATUS_TONES: Record<ProgressStatus, "neutral" | "indigo" | "teal"> = {
  not_started: "neutral",
  in_progress: "indigo",
  completed: "teal",
};

interface ResourceProgressSectionProps {
  resource: Resource;
}

/**
 * Tracks and surfaces reading/watch progress for one resource, inside
 * ResourceDetailDialog -- composed the same way ProcessingPanel/
 * EmbeddingPanel/ExtractionPanel already are. Renders:
 *   - a status header (badge + percent + progress bar), always
 *   - an embedded, position-tracking video player, for video resources with
 *     a playable source (YouTube or a direct file URL)
 *   - the resource's saved content as a scroll-tracked reading pane, for
 *     any non-video resource that has one
 *   - a "Mark as complete" action, always (the fallback when neither of the
 *     above can auto-track -- e.g. a URL resource with no pasted content,
 *     or a video source that can't be embedded)
 */
export function ResourceProgressSection({ resource }: ResourceProgressSectionProps) {
  const { progress, loading, save, flush, markComplete } = useResourceProgress(resource.id);
  const [completing, setCompleting] = useState(false);
  const [completeError, setCompleteError] = useState<string | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const restoredScrollRef = useRef(false);

  // Flush any pending throttled save when the dialog closes for this resource.
  useEffect(() => {
    return () => flush();
  }, [flush]);

  // Restore scroll position once, as soon as both the content pane and the
  // fetched progress are available.
  useEffect(() => {
    if (restoredScrollRef.current) return;
    const el = contentRef.current;
    if (!el || !progress) return;
    const scrollable = el.scrollHeight - el.clientHeight;
    if (scrollable > 0 && progress.progressPercent > 0) {
      el.scrollTop = (progress.progressPercent / 100) * scrollable;
    }
    restoredScrollRef.current = true;
  }, [progress]);

  function handleContentScroll(event: React.UIEvent<HTMLDivElement>) {
    const el = event.currentTarget;
    const scrollable = el.scrollHeight - el.clientHeight;
    if (scrollable <= 0) return;
    const percent = Math.min(100, Math.max(0, (el.scrollTop / scrollable) * 100));
    save({ progressPercent: Math.round(percent) });
  }

  async function handleMarkComplete() {
    setCompleting(true);
    setCompleteError(null);
    try {
      await markComplete();
    } catch (err) {
      setCompleteError(err instanceof ApiError ? err.message : "Failed to update progress.");
    } finally {
      setCompleting(false);
    }
  }

  if (loading || !progress) {
    return null;
  }

  const isVideo = resource.type === "video";
  const isCompleted = progress.status === "completed";
  const hasReadableContent = !isVideo && Boolean(resource.content);

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-base-border bg-base-elevated/40 px-3.5 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          {isCompleted ? (
            <IconCheckCircle className="h-4 w-4 shrink-0 text-accent-teal" />
          ) : (
            <IconClock className="h-4 w-4 shrink-0 text-content-muted" />
          )}
          <div>
            <p className="text-sm font-medium text-content-primary">
              {isVideo ? "Watch progress" : "Reading progress"}
            </p>
            <div className="mt-1 flex items-center gap-2">
              <Badge tone={STATUS_TONES[progress.status]}>{STATUS_LABELS[progress.status]}</Badge>
              {progress.progressPercent > 0 && (
                <span className="text-xs text-content-muted">
                  {Math.round(progress.progressPercent)}%
                </span>
              )}
            </div>
          </div>
        </div>
        {!isCompleted && (
          <Button size="sm" variant="secondary" onClick={handleMarkComplete} loading={completing}>
            Mark as complete
          </Button>
        )}
      </div>

      {progress.progressPercent > 0 && <ProgressBar percent={progress.progressPercent} />}

      {isVideo && resource.sourceUrl && (
        <VideoProgressPlayer
          sourceUrl={resource.sourceUrl}
          initialProgress={progress}
          onSave={save}
          onFlush={flush}
        />
      )}

      {hasReadableContent && (
        <div
          ref={contentRef}
          onScroll={handleContentScroll}
          className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-xl border border-base-border bg-base px-3.5 py-3 text-sm leading-relaxed text-content-secondary"
        >
          {resource.content}
        </div>
      )}

      {completeError && <p className="text-xs text-danger">{completeError}</p>}
    </div>
  );
}
