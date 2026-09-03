import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils/cn";

type BadgeTone = "neutral" | "indigo" | "teal" | "danger";

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: "bg-base-elevated text-content-secondary",
  indigo: "bg-accent-indigo/10 text-accent-indigo",
  teal: "bg-accent-teal/10 text-accent-teal",
  danger: "bg-danger/10 text-danger",
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  icon?: ReactNode;
}

/** Small rounded pill for resource types, statuses, and tags. */
export function Badge({ tone = "neutral", icon, className, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium leading-none",
        TONE_CLASSES[tone],
        className
      )}
      {...props}
    >
      {icon}
      {children}
    </span>
  );
}
