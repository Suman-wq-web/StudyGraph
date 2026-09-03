"use client";

import { useEffect, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { IconPath } from "@/components/ui/icons";
import { RecommendationCard } from "@/components/recommendations/RecommendationCard";
import { ApiError } from "@/lib/api/client";
import { getRecommendations } from "@/lib/api/recommendations";
import type { RecommendationResponse } from "@/lib/types/recommendation";

export default function RecommendationsPage() {
  const [data, setData] = useState<RecommendationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    getRecommendations()
      .then(setData)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Failed to load recommendations.");
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <Topbar title="Learning Path" />
      <main className="mx-auto flex w-full max-w-4xl animate-fade-in flex-col gap-6 p-6 sm:p-8 lg:p-10">
        <PageHeader
          title="Learning Path"
          description="Personalized suggestions for what to learn next, based on gaps and connections found in your knowledge graph."
          actions={
            data ? <Badge tone="indigo">{data.items.length} suggestion{data.items.length === 1 ? "" : "s"}</Badge> : undefined
          }
        />

        {loading && (
          <Card>
            <LoadingState message="Analyzing your knowledge graph..." />
          </Card>
        )}

        {!loading && error && (
          <Card>
            <ErrorState message={error} onRetry={load} />
          </Card>
        )}

        {!loading && !error && data && data.items.length === 0 && (
          <Card>
            <EmptyState
              icon={<IconPath className="h-5 w-5" />}
              title="No recommendations yet"
              description="Once your knowledge graph has enough concepts and connections, personalized 'what to learn next' suggestions will appear here."
            />
          </Card>
        )}

        {!loading && !error && data && data.items.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {data.items.map((item) => (
              <RecommendationCard key={`${item.reasonType}-${item.conceptId}`} recommendation={item} />
            ))}
          </div>
        )}
      </main>
    </>
  );
}
