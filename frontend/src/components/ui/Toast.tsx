import { IconCheckCircle, IconAlertTriangle, IconClose } from "@/components/ui/icons";
import { cn } from "@/lib/utils/cn";
import type { ToastItem } from "@/lib/hooks/useToast";

interface ToastStackProps {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}

/** Fixed bottom-right stack of transient success/error notifications. */
export function ToastStack({ toasts, onDismiss }: ToastStackProps) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[60] flex w-full max-w-sm flex-col gap-2 sm:bottom-6 sm:right-6">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role="status"
          className={cn(
            "flex animate-fade-in items-start gap-2.5 rounded-xl border bg-base-surface px-4 py-3 shadow-lg",
            toast.tone === "error" ? "border-danger/30" : "border-accent-teal/30"
          )}
        >
          {toast.tone === "error" ? (
            <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
          ) : (
            <IconCheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-accent-teal" />
          )}
          <p className="flex-1 text-sm text-content-primary">{toast.message}</p>
          <button
            onClick={() => onDismiss(toast.id)}
            aria-label="Dismiss notification"
            className="text-content-muted hover:text-content-primary"
          >
            <IconClose className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
