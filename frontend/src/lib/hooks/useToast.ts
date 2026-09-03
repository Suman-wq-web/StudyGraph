"use client";

import { useCallback, useRef, useState } from "react";

export type ToastTone = "success" | "error";

export interface ToastItem {
  id: string;
  message: string;
  tone: ToastTone;
}

const AUTO_DISMISS_MS = 3500;

/** Local (per-page) toast queue -- no global provider needed for a single page's mutations. */
export function useToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (message: string, tone: ToastTone = "success") => {
      const id = `toast-${nextId.current++}`;
      setToasts((prev) => [...prev, { id, message, tone }]);
      setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    },
    [dismiss]
  );

  return { toasts, push, dismiss };
}
