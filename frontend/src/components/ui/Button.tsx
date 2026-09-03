import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils/cn";
import { IconSpinner } from "@/components/ui/icons";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-accent-indigo text-white hover:opacity-90 shadow-sm shadow-accent-indigo/20",
  secondary:
    "bg-base-elevated text-content-primary border border-base-border hover:border-accent-teal/50",
  ghost: "text-content-secondary hover:text-content-primary hover:bg-base-elevated",
  danger: "bg-danger text-white hover:opacity-90 shadow-sm shadow-danger/20",
};

const sizeClasses: Record<Size, string> = {
  sm: "px-3 py-1.5 text-xs",
  md: "px-4 py-2 text-sm",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", loading = false, disabled, children, ...props }, ref) => (
    <button
      ref={ref}
      disabled={disabled || loading}
      aria-busy={loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-colors duration-150 disabled:opacity-50 disabled:pointer-events-none",
        variantClasses[variant],
        sizeClasses[size],
        className
      )}
      {...props}
    >
      {loading && <IconSpinner className="h-3.5 w-3.5" />}
      {children}
    </button>
  )
);
Button.displayName = "Button";
