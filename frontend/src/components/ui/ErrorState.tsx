import { IconAlertTriangle } from "@/components/ui/icons";
import { Button } from "@/components/ui/Button";

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({ message = "Something went wrong.", onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-danger/20 bg-danger/5 px-6 py-16 text-center">
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-danger/10 text-danger">
        <IconAlertTriangle className="h-5 w-5" />
      </div>
      <p className="max-w-sm text-sm font-medium text-danger">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
