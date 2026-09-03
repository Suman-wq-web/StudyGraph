"use client";

import { useEffect, type ReactNode } from "react";
import { cn } from "@/lib/utils/cn";
import { IconClose } from "@/components/ui/icons";

interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}

/** Centered overlay dialog. Closes on backdrop click or Escape. */
export function Modal({ title, onClose, children, className }: ModalProps) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 animate-fade-in-backdrop bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          "relative flex max-h-[85vh] w-full max-w-lg animate-scale-in flex-col overflow-hidden rounded-2xl border border-base-border bg-base-surface shadow-xl",
          className
        )}
      >
        <div className="flex items-center justify-between border-b border-base-border px-5 py-4">
          <h2 className="text-sm font-semibold text-content-primary">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="flex h-7 w-7 items-center justify-center rounded-lg text-content-secondary transition-colors hover:bg-base-elevated hover:text-content-primary"
          >
            <IconClose className="h-4 w-4" />
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>
  );
}
