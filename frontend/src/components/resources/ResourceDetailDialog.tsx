"use client";

import { useEffect, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import {
  IconAlertTriangle,
  IconArticle,
  IconCalendar,
  IconCheckCircle,
  IconClock,
  IconExternalLink,
  IconNote,
  IconSparkles,
  IconSpinner,
  IconUrl,
  IconVideo,
} from "@/components/ui/icons";
import { ApiError } from "@/lib/api/client";
import {
  embedResource,
  extractResource,
  getEmbeddingStatus,
  getExtractionStatus,
  getProcessingStatus,
  processResource,
} from "@/lib/api/resources";
import { ResourceProgressSection } from "@/components/resources/ResourceProgressSection";
import {
  RESOURCE_TYPE_LABELS,
  type EmbeddingStatusResponse,
  type ProcessingStatusResponse,
  type Resource,
  type ResourceType,
} from "@/lib/types/resource";
import type { ExtractionStatusResponse } from "@/lib/types/graph";

const TYPE_ICONS: Record<ResourceType, typeof IconArticle> = {
  article: IconArticle,
  video: IconVideo,
  url: IconUrl,
  note: IconNote,
};

const POLL_INTERVAL_MS = 1500;

interface ResourceDetailDialogProps {
  resource: Resource;
  onClose: () => void;
  onEdit: () => void;
  onDelete: () => void;
  /** Bubbles a status change up so the Library list/card stay in sync. */
  onProcessed: (resource: Resource) => void;
}

export function ResourceDetailDialog({
  resource,
  onClose,
  onEdit,
  onDelete,
  onProcessed,
}: ResourceDetailDialogProps) {
  const TypeIcon = TYPE_ICONS[resource.type];

  return (
    <Modal
      title="Resource details"
      onClose={onClose}
      className={resource.type === "video" ? "max-w-2xl" : undefined}
    >
      <div className="flex flex-col gap-5">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-base-elevated text-content-secondary">
            <TypeIcon className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h3 className="text-base font-semibold leading-snug text-content-primary">
              {resource.title}
            </h3>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <Badge tone="indigo">{RESOURCE_TYPE_LABELS[resource.type]}</Badge>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-content-muted">
          <span className="flex items-center gap-1.5">
            <IconCalendar className="h-3.5 w-3.5" />
            Added {new Date(resource.createdAt).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
              year: "numeric",
            })}
          </span>
          {resource.updatedAt !== resource.createdAt && (
            <span>
              Updated{" "}
              {new Date(resource.updatedAt).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
            </span>
          )}
        </div>

        <ProcessingPanel resource={resource} onProcessed={onProcessed} />
        <EmbeddingPanel resource={resource} onProcessed={onProcessed} />
        <ExtractionPanel resource={resource} />

        {resource.sourceUrl && (
          <a
            href={resource.sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 break-all rounded-xl border border-base-border bg-base-elevated px-3 py-2 text-sm text-accent-indigo transition-colors hover:border-accent-indigo/40"
          >
            <IconExternalLink className="h-3.5 w-3.5 shrink-0" />
            {resource.sourceUrl}
          </a>
        )}

        {resource.description && (
          <p className="text-sm leading-relaxed text-content-secondary">{resource.description}</p>
        )}

        <ResourceProgressSection resource={resource} />

        {resource.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {resource.tags.map((tag) => (
              <span
                key={tag}
                className="rounded-full bg-base-elevated px-2.5 py-1 text-xs text-content-secondary"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        <div className="flex justify-end gap-2 border-t border-base-border pt-4">
          <Button variant="ghost" onClick={onDelete} className="text-danger hover:bg-danger/10 hover:text-danger">
            Delete
          </Button>
          <Button variant="secondary" onClick={onEdit}>
            Edit
          </Button>
          <Button onClick={onClose}>Close</Button>
        </div>
      </div>
    </Modal>
  );
}

interface PipelinePanelProps {
  resource: Resource;
  onProcessed: (resource: Resource) => void;
}

/** Surfaces the chunking (Phase 3) lifecycle: trigger, in-progress, completed, failed. */
function ProcessingPanel({ resource, onProcessed }: PipelinePanelProps) {
  const [statusInfo, setStatusInfo] = useState<ProcessingStatusResponse | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [triggerError, setTriggerError] = useState<string | null>(null);

  const liveStatus = statusInfo?.status ?? resource.status;
  const liveError = statusInfo?.processingError ?? resource.processingError;
  const chunkCount = statusInfo?.chunkCount ?? 0;
  // `resource.status` is shared with the embedding stage (see
  // backend/app/models/resource.py's ResourceStatus), so `failed` alone
  // doesn't tell us which stage actually failed. chunkCount > 0 is direct
  // evidence chunking already produced output, which means a later stage
  // (embedding) is what's currently broken, not this one.
  const chunkingFailed = liveStatus === "failed" && chunkCount === 0;
  const chunkingDone = liveStatus !== "pending" && liveStatus !== "processing" && !chunkingFailed;

  useEffect(() => {
    let cancelled = false;
    getProcessingStatus(resource.id)
      .then((info) => {
        if (!cancelled) setStatusInfo(info);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [resource.id]);

  useEffect(() => {
    if (liveStatus !== "processing") return;
    const interval = setInterval(async () => {
      try {
        const info = await getProcessingStatus(resource.id);
        setStatusInfo(info);
        if (info.status !== "processing") {
          onProcessed({
            ...resource,
            status: info.status,
            processingError: info.processingError,
            updatedAt: info.updatedAt,
          });
        }
      } catch {
        // Transient poll failure -- try again next tick.
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveStatus, resource.id]);

  async function handleProcess() {
    setTriggering(true);
    setTriggerError(null);
    try {
      const updated = await processResource(resource.id);
      onProcessed(updated);
      setStatusInfo({
        resourceId: updated.id,
        status: updated.status,
        chunkCount: statusInfo?.chunkCount ?? 0,
        processingError: updated.processingError,
        updatedAt: updated.updatedAt,
      });
    } catch (err) {
      setTriggerError(err instanceof ApiError ? err.message : "Failed to start processing.");
    } finally {
      setTriggering(false);
    }
  }

  const isBusy = liveStatus === "processing" || liveStatus === "embedding";
  const buttonLabel = liveStatus === "pending" ? "Process" : "Reprocess";

  return (
    <div className="rounded-xl border border-base-border bg-base-elevated/40 px-3.5 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          {chunkingFailed && <IconAlertTriangle className="h-4 w-4 shrink-0 text-danger" />}
          {!chunkingFailed && liveStatus === "processing" && (
            <IconSpinner className="h-4 w-4 shrink-0 text-accent-indigo" />
          )}
          {!chunkingFailed && chunkingDone && (
            <IconCheckCircle className="h-4 w-4 shrink-0 text-accent-teal" />
          )}
          {!chunkingFailed && liveStatus === "pending" && (
            <IconClock className="h-4 w-4 shrink-0 text-content-muted" />
          )}
          <div>
            <p className="text-sm font-medium text-content-primary">
              {liveStatus === "pending" && "Not chunked yet"}
              {liveStatus === "processing" && "Chunking..."}
              {chunkingDone && "Chunked"}
              {chunkingFailed && "Chunking failed"}
            </p>
            <p className="text-xs text-content-muted">
              {chunkingDone &&
                (statusInfo?.chunkCount !== undefined
                  ? `${statusInfo.chunkCount} chunk${statusInfo.chunkCount === 1 ? "" : "s"}.`
                  : "Split into chunks.")}
              {liveStatus === "processing" && "Extracting and chunking content..."}
              {liveStatus === "pending" && "Split this resource's text into chunks for future embedding."}
              {chunkingFailed && (liveError ?? "Something went wrong.")}
            </p>
          </div>
        </div>
        <Button size="sm" variant="secondary" onClick={handleProcess} loading={triggering} disabled={isBusy}>
          {buttonLabel}
        </Button>
      </div>
      {triggerError && <p className="mt-2 text-xs text-danger">{triggerError}</p>}
    </div>
  );
}

/** Surfaces the embedding (Phase 4) lifecycle: trigger, in-progress, completed, failed. */
function EmbeddingPanel({ resource, onProcessed }: PipelinePanelProps) {
  const [statusInfo, setStatusInfo] = useState<EmbeddingStatusResponse | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [triggerError, setTriggerError] = useState<string | null>(null);

  const liveStatus = statusInfo?.status ?? resource.status;
  const liveError = statusInfo?.processingError ?? resource.processingError;
  const totalChunkCount = statusInfo?.totalChunkCount ?? 0;
  const embeddedChunkCount = statusInfo?.embeddedChunkCount ?? 0;
  // Mirrors ProcessingPanel's reasoning: `failed` can also come from a
  // *later* chunking failure (Reprocess) after this resource was already
  // fully embedded once. Every chunk that currently exists already having
  // a vector means embedding itself isn't what's currently broken.
  const embeddingComplete = totalChunkCount > 0 && embeddedChunkCount === totalChunkCount;
  const embeddingFailed = liveStatus === "failed" && !embeddingComplete;
  const canTrigger = liveStatus === "ready" || liveStatus === "embedded" || liveStatus === "failed";

  useEffect(() => {
    let cancelled = false;
    getEmbeddingStatus(resource.id)
      .then((info) => {
        if (!cancelled) setStatusInfo(info);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [resource.id]);

  useEffect(() => {
    if (liveStatus !== "embedding") return;
    const interval = setInterval(async () => {
      try {
        const info = await getEmbeddingStatus(resource.id);
        setStatusInfo(info);
        if (info.status !== "embedding") {
          onProcessed({
            ...resource,
            status: info.status,
            processingError: info.processingError,
            updatedAt: info.updatedAt,
          });
        }
      } catch {
        // Transient poll failure -- try again next tick.
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveStatus, resource.id]);

  async function handleEmbed() {
    setTriggering(true);
    setTriggerError(null);
    try {
      const updated = await embedResource(resource.id);
      onProcessed(updated);
      setStatusInfo({
        resourceId: updated.id,
        status: updated.status,
        embeddedChunkCount: statusInfo?.embeddedChunkCount ?? 0,
        totalChunkCount: statusInfo?.totalChunkCount ?? 0,
        processingError: updated.processingError,
        updatedAt: updated.updatedAt,
      });
    } catch (err) {
      setTriggerError(err instanceof ApiError ? err.message : "Failed to start embedding.");
    } finally {
      setTriggering(false);
    }
  }

  if (liveStatus === "pending" || liveStatus === "processing") {
    return null; // nothing to embed yet -- chunk first
  }

  return (
    <div className="rounded-xl border border-base-border bg-base-elevated/40 px-3.5 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          {liveStatus === "embedding" && <IconSpinner className="h-4 w-4 shrink-0 text-accent-indigo" />}
          {liveStatus !== "embedding" && embeddingFailed && (
            <IconAlertTriangle className="h-4 w-4 shrink-0 text-danger" />
          )}
          {liveStatus !== "embedding" && !embeddingFailed && embeddingComplete && (
            <IconSparkles className="h-4 w-4 shrink-0 text-accent-teal" />
          )}
          {liveStatus !== "embedding" && !embeddingFailed && !embeddingComplete && (
            <IconClock className="h-4 w-4 shrink-0 text-content-muted" />
          )}
          <div>
            <p className="text-sm font-medium text-content-primary">
              {liveStatus === "embedding" && "Embedding..."}
              {liveStatus !== "embedding" && embeddingFailed && "Embedding failed"}
              {liveStatus !== "embedding" && !embeddingFailed && embeddingComplete && "Embedded"}
              {liveStatus !== "embedding" && !embeddingFailed && !embeddingComplete && "Not embedded yet"}
            </p>
            <p className="text-xs text-content-muted">
              {liveStatus === "embedding" && "Generating embeddings with Gemini..."}
              {liveStatus !== "embedding" && embeddingFailed && (liveError ?? "Something went wrong.")}
              {liveStatus !== "embedding" &&
                !embeddingFailed &&
                embeddingComplete &&
                `${embeddedChunkCount}/${totalChunkCount} chunks embedded with Gemini.`}
              {liveStatus !== "embedding" &&
                !embeddingFailed &&
                !embeddingComplete &&
                "Generate embeddings so this resource is searchable by meaning."}
            </p>
          </div>
        </div>
        {canTrigger && (
          <Button size="sm" variant="secondary" onClick={handleEmbed} loading={triggering}>
            {embeddingComplete ? "Re-embed" : "Embed"}
          </Button>
        )}
      </div>
      {triggerError && <p className="mt-2 text-xs text-danger">{triggerError}</p>}
    </div>
  );
}

/**
 * Surfaces the concept/relationship extraction (Phase 6) lifecycle: trigger,
 * in-progress, completed. Unlike ProcessingPanel/EmbeddingPanel, there's no
 * `Resource.status` value for this stage (see
 * backend/app/services/graph_extraction_service.py for why) -- "in
 * progress" is inferred from `extractedChunkCount` still trailing
 * `totalChunkCount` while polling after a trigger.
 */
function ExtractionPanel({ resource }: { resource: Resource }) {
  const [statusInfo, setStatusInfo] = useState<ExtractionStatusResponse | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [polling, setPolling] = useState(false);
  const [triggerError, setTriggerError] = useState<string | null>(null);

  const canTrigger = resource.status !== "pending" && resource.status !== "processing";

  useEffect(() => {
    if (!canTrigger) return;
    let cancelled = false;
    getExtractionStatus(resource.id)
      .then((info) => {
        if (!cancelled) setStatusInfo(info);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resource.id, canTrigger]);

  useEffect(() => {
    if (!polling) return;
    const interval = setInterval(async () => {
      try {
        const info = await getExtractionStatus(resource.id);
        setStatusInfo(info);
        if (info.extractedChunkCount >= info.totalChunkCount) {
          setPolling(false);
        }
      } catch {
        // Transient poll failure -- try again next tick.
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [polling, resource.id]);

  if (!canTrigger) {
    return null; // nothing to extract from yet -- chunk first
  }

  async function handleExtract() {
    setTriggering(true);
    setTriggerError(null);
    try {
      const trigger = await extractResource(resource.id);
      const info = await getExtractionStatus(resource.id);
      setStatusInfo(info);
      setPolling(trigger.chunksPending > 0 && info.extractedChunkCount < info.totalChunkCount);
    } catch (err) {
      setTriggerError(err instanceof ApiError ? err.message : "Failed to start extraction.");
    } finally {
      setTriggering(false);
    }
  }

  const isComplete =
    statusInfo !== null && statusInfo.totalChunkCount > 0 && statusInfo.extractedChunkCount >= statusInfo.totalChunkCount;

  return (
    <div className="rounded-xl border border-base-border bg-base-elevated/40 px-3.5 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          {polling && <IconSpinner className="h-4 w-4 shrink-0 text-accent-indigo" />}
          {!polling && isComplete && <IconCheckCircle className="h-4 w-4 shrink-0 text-accent-teal" />}
          {!polling && !isComplete && <IconClock className="h-4 w-4 shrink-0 text-content-muted" />}
          <div>
            <p className="text-sm font-medium text-content-primary">
              {polling && "Extracting concepts..."}
              {!polling && isComplete && "Concepts extracted"}
              {!polling && !isComplete && "Concepts not extracted yet"}
            </p>
            <p className="text-xs text-content-muted">
              {statusInfo && statusInfo.totalChunkCount > 0
                ? `${statusInfo.extractedChunkCount}/${statusInfo.totalChunkCount} chunks processed.`
                : "Identify the concepts and relationships this resource teaches, for the knowledge graph."}
            </p>
          </div>
        </div>
        <Button size="sm" variant="secondary" onClick={handleExtract} loading={triggering} disabled={polling}>
          {isComplete ? "Re-extract" : "Extract"}
        </Button>
      </div>
      {triggerError && <p className="mt-2 text-xs text-danger">{triggerError}</p>}
    </div>
  );
}
