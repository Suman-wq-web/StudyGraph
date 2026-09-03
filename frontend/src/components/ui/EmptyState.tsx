import type { ReactNode } from "react";
import { IconInbox } from "@/components/ui/icons";

interface EmptyStateProps {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: ReactNode;
}

export function EmptyState({ title, description, action, icon }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-base-border px-6 py-16 text-center">
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-base-elevated text-content-muted">
        {icon ?? <IconInbox className="h-5 w-5" />}
      </div>
      <p className="text-sm font-medium text-content-primary">{title}</p>
      <p className="max-w-sm text-sm text-content-muted">{description}</p>
      {action}
    </div>
  );
}
