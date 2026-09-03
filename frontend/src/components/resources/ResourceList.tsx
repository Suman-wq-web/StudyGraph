import type { ReactNode } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Card } from "@/components/ui/Card";
import { IconLibrary } from "@/components/ui/icons";
import { ResourceCard } from "@/components/resources/ResourceCard";
import type { Resource } from "@/lib/types/resource";

interface ResourceListProps {
  resources?: Resource[];
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  onSelect?: (resource: Resource) => void;
  onEdit?: (resource: Resource) => void;
  onDelete?: (resource: Resource) => void;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: ReactNode;
}

function ResourceCardSkeleton() {
  return (
    <Card>
      <div className="flex items-start gap-4">
        <Skeleton className="h-10 w-10 shrink-0 rounded-xl" />
        <div className="flex-1 flex-col gap-2">
          <div className="flex gap-1.5">
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-5 w-14 rounded-full" />
          </div>
          <Skeleton className="mt-2 h-4 w-2/3 rounded" />
          <Skeleton className="mt-2 h-3 w-1/3 rounded" />
        </div>
        <Skeleton className="h-4 w-14 shrink-0 rounded" />
      </div>
    </Card>
  );
}

/** Renders a resource library: loading skeletons, an error state, an empty state, or the list. */
export function ResourceList({
  resources = [],
  loading = false,
  error = null,
  onRetry,
  onSelect,
  onEdit,
  onDelete,
  emptyTitle = "No resources yet",
  emptyDescription = "Saved articles, videos, URLs, and notes will show up here once ingestion is implemented.",
  emptyAction,
}: ResourceListProps) {
  if (loading) {
    return (
      <div className="flex flex-col gap-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <ResourceCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (error) {
    return <ErrorState message={error} onRetry={onRetry} />;
  }

  if (resources.length === 0) {
    return (
      <EmptyState
        title={emptyTitle}
        description={emptyDescription}
        icon={<IconLibrary className="h-5 w-5" />}
        action={emptyAction}
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {resources.map((resource) => (
        <ResourceCard
          key={resource.id}
          resource={resource}
          onSelect={onSelect}
          onEdit={onEdit}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}
