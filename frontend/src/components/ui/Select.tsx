import { forwardRef, type SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils/cn";
import { IconChevronDown } from "@/components/ui/icons";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, className, id, children, ...props }, ref) => {
    const selectId = id ?? props.name;
    return (
      <label className="flex flex-col gap-1.5" htmlFor={selectId}>
        {label && <span className="text-xs font-medium text-content-secondary">{label}</span>}
        <div className="relative">
          <select
            ref={ref}
            id={selectId}
            aria-invalid={Boolean(error)}
            className={cn(
              "w-full appearance-none rounded-xl border bg-base-surface px-3 py-2 pr-9 text-sm text-content-primary transition-colors focus:outline-none focus:ring-2 disabled:opacity-50",
              error
                ? "border-danger/50 focus:ring-danger/30"
                : "border-base-border focus:border-accent-indigo/50 focus:ring-accent-indigo/20",
              className
            )}
            {...props}
          >
            {children}
          </select>
          <IconChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-content-muted" />
        </div>
        {error && <span className="text-xs text-danger">{error}</span>}
      </label>
    );
  }
);
Select.displayName = "Select";
