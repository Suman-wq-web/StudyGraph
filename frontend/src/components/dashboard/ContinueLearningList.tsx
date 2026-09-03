"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { IconArticle, IconClock, IconNote, IconPlay, IconUrl, IconVideo } from "@/components/ui/icons";
import { ApiError } from "@/lib/api/client";
import { listInProgressResources } from "@/lib/api/progress";
import type { InProgressResource } from "@/lib/types/progress";
import type { ResourceType } from "@/lib/types/resource";

const TYPE_ICONS: Record<ResourceType, typeof IconArticle> = {
  article: IconArticle,
  video: IconVideo,
  url: IconUrl,
  note: IconNote,
};

const LIMIT = 5;

/** The Dashboard's "Continue learning" card body: this user's in-progress
 * resources (GET /resources/progress/in-progress), each resuming into the
 * same ResourceDetailDialog the Library page already uses via its
 * `?resource=` deep link. */
export function ContinueLearningList() {
  const router = useRouter();
  const [items, setItems] = useState<InProgressResource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function fetchItems() {
    setLoading(true);
    setError(null);
    listInProgressResources(LIMIT)
      .then((res) => setItems(res.items))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Failed to load progress.")
      )
      .finally(() => setLoading(false));
  }

  useEffect(fetchItems, []);

  if (loading) {
    return (
      <div className="flex flex-col gap-3">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <Skeleton className="h-9 w-9 shrink-0 rounded-xl" />
            <div className="flex-1">
              <Skeleton className="h-3.5 w-2/3 rounded" />
              <Skeleton className="mt-2 h-1.5 w-full rounded-full" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return <ErrorState message={error} onRetry={fetchItems} />;
  }

  if (items.length === 0) {
    return (
      <EmptyState
        icon={<IconClock className="h-5 w-5" />}
        title="Nothing in progress"
        description="Once you start reading or watching something, it'll show up here so you can pick up where you left off."
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {items.map((item) => {
        const TypeIcon = TYPE_ICONS[item.type];
        return (
          <button
            key={item.resourceId}
            onClick={() => router.push(`/library?resource=${item.resourceId}`)}
            className="group flex items-center gap-3 rounded-xl text-left transition-colors hover:bg-base-elevated/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-indigo/40"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-base-elevated text-content-secondary">
              <TypeIcon className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-content-primary">{item.title}</p>
              <div className="mt-1.5 flex items-center gap-2">
                <ProgressBar percent={item.progressPercent} className="flex-1" />
                <span className="shrink-0 text-[11px] text-content-muted">
                  {Math.round(item.progressPercent)}%
                </span>
              </div>
            </div>
            <IconPlay className="h-4 w-4 shrink-0 text-content-muted transition-colors group-hover:text-accent-indigo" />
          </button>
        );
      })}
    </div>
  );
}
