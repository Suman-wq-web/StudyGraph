import { cn } from "@/lib/utils/cn";

interface ProgressBarProps {
  /** 0-100. Values outside that range are clamped. */
  percent: number;
  className?: string;
  trackClassName?: string;
  barClassName?: string;
}

/** Thin horizontal progress indicator, shared by the Dashboard's Continue
 * Learning list and the resource detail view's video/reading progress. */
export function ProgressBar({ percent, className, trackClassName, barClassName }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, percent));
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-base-elevated", trackClassName, className)}
    >
      <div
        className={cn("h-full rounded-full bg-accent-indigo transition-[width] duration-300", barClassName)}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
