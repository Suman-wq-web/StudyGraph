"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { completeProgress, getProgress, updateProgress } from "@/lib/api/progress";
import type { ProgressUpdateInput, ResourceProgress } from "@/lib/types/progress";

const SAVE_INTERVAL_MS = 5000;

/**
 * Fetches a resource's progress once, then exposes a throttled `save()` for
 * video/reading trackers to call as often as they like (every timeupdate/
 * scroll event) without spamming the API -- at most one PATCH every
 * SAVE_INTERVAL_MS, with the most recent payload winning, plus `flush()` to
 * force an immediate save (pause, scroll end, unmount) so nothing's lost.
 */
export function useResourceProgress(resourceId: string) {
  const [progress, setProgress] = useState<ResourceProgress | null>(null);
  const [loading, setLoading] = useState(true);
  const lastSaveAtRef = useRef(0);
  const pendingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingPayloadRef = useRef<ProgressUpdateInput | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getProgress(resourceId)
      .then((result) => {
        if (!cancelled) setProgress(result);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [resourceId]);

  const flush = useCallback(() => {
    if (pendingTimeoutRef.current) {
      clearTimeout(pendingTimeoutRef.current);
      pendingTimeoutRef.current = null;
    }
    const payload = pendingPayloadRef.current;
    pendingPayloadRef.current = null;
    if (!payload) return;
    lastSaveAtRef.current = Date.now();
    updateProgress(resourceId, payload)
      .then(setProgress)
      .catch(() => {
        // Transient failure -- the next throttled save (or reopening the
        // resource) will retry; not worth surfacing a toast for a
        // background autosave.
      });
  }, [resourceId]);

  const save = useCallback(
    (payload: ProgressUpdateInput, options?: { immediate?: boolean }) => {
      pendingPayloadRef.current = { ...pendingPayloadRef.current, ...payload };
      const elapsed = Date.now() - lastSaveAtRef.current;
      if (options?.immediate || elapsed >= SAVE_INTERVAL_MS) {
        flush();
        return;
      }
      if (!pendingTimeoutRef.current) {
        pendingTimeoutRef.current = setTimeout(flush, SAVE_INTERVAL_MS - elapsed);
      }
    },
    [flush]
  );

  const markComplete = useCallback(async () => {
    const updated = await completeProgress(resourceId);
    setProgress(updated);
    return updated;
  }, [resourceId]);

  useEffect(() => {
    return () => {
      if (pendingTimeoutRef.current) clearTimeout(pendingTimeoutRef.current);
    };
  }, []);

  return { progress, loading, save, flush, markComplete };
}
