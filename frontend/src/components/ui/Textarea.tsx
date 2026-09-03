import { forwardRef, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils/cn";

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  helperText?: string;
  error?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, helperText, error, className, id, ...props }, ref) => {
    const textareaId = id ?? props.name;
    return (
      <label className="flex flex-col gap-1.5" htmlFor={textareaId}>
        {label && <span className="text-xs font-medium text-content-secondary">{label}</span>}
        <textarea
          ref={ref}
          id={textareaId}
          aria-invalid={Boolean(error)}
          className={cn(
            "w-full resize-none rounded-xl border bg-base-surface px-3 py-2 text-sm text-content-primary placeholder:text-content-muted transition-colors focus:outline-none focus:ring-2 disabled:opacity-50",
            error
              ? "border-danger/50 focus:ring-danger/30"
              : "border-base-border focus:border-accent-indigo/50 focus:ring-accent-indigo/20",
            className
          )}
          {...props}
        />
        {error ? (
          <span className="text-xs text-danger">{error}</span>
        ) : helperText ? (
          <span className="text-xs text-content-muted">{helperText}</span>
        ) : null}
      </label>
    );
  }
);
Textarea.displayName = "Textarea";
