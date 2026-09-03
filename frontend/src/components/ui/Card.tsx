import { type HTMLAttributes } from "react";
import { cn } from "@/lib/utils/cn";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Adds hover/focus affordance for cards that act as click targets. */
  interactive?: boolean;
}

/** Base surface for dashboard cards, panels, and list items. Subtle glass edge, no heavy blur. */
export function Card({ className, interactive = false, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-base-border bg-base-surface/80 backdrop-blur-sm p-5 shadow-sm transition-all duration-150",
        interactive &&
          "cursor-pointer hover:-translate-y-0.5 hover:border-accent-indigo/30 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-indigo/40",
        className
      )}
      {...props}
    />
  );
}
