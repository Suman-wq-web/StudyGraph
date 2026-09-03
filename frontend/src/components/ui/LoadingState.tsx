import { IconSpinner } from "@/components/ui/icons";

interface LoadingStateProps {
  message?: string;
}

/** Centered spinner for full-section loads (as opposed to `Skeleton`, used for list placeholders). */
export function LoadingState({ message = "Loading..." }: LoadingStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <IconSpinner className="h-5 w-5 text-content-muted" />
      <p className="text-sm text-content-muted">{message}</p>
    </div>
  );
}
