import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils/cn";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  helperText?: string;
  error?: string;
  icon?: ReactNode;
  trailing?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, helperText, error, icon, trailing, className, id, ...props }, ref) => {
    const inputId = id ?? props.name;
    return (
      <label className="flex flex-col gap-1.5" htmlFor={inputId}>
        {label && (
          <span className="text-xs font-medium text-content-secondary">
            {label}
            {props.required && <span className="ml-0.5 text-accent-indigo">*</span>}
          </span>
        )}
        <div className="relative flex items-center">
          {icon && (
            <span className="pointer-events-none absolute left-3 flex h-4 w-4 items-center justify-center text-content-muted">
              {icon}
            </span>
          )}
          <input
            ref={ref}
            id={inputId}
            aria-invalid={Boolean(error)}
            className={cn(
              "w-full rounded-xl border bg-base-surface px-3 py-2 text-sm text-content-primary placeholder:text-content-muted transition-colors focus:outline-none focus:ring-2 disabled:opacity-50",
              icon && "pl-9",
              trailing && "pr-9",
              error
                ? "border-danger/50 focus:ring-danger/30"
                : "border-base-border focus:border-accent-indigo/50 focus:ring-accent-indigo/20",
              className
            )}
            {...props}
          />
          {trailing && <span className="absolute right-3 flex items-center">{trailing}</span>}
        </div>
        {error ? (
          <span className="text-xs text-danger">{error}</span>
        ) : helperText ? (
          <span className="text-xs text-content-muted">{helperText}</span>
        ) : null}
      </label>
    );
  }
);
Input.displayName = "Input";
