"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatCard } from "@/components/dashboard/StatCard";
import { Card } from "@/components/ui/Card";
import { ResourceList } from "@/components/resources/ResourceList";
import { ContinueLearningList } from "@/components/dashboard/ContinueLearningList";
import { Button } from "@/components/ui/Button";
import { IconArticle, IconLibrary, IconNote, IconPlus, IconVideo } from "@/components/ui/icons";
import { ApiError } from "@/lib/api/client";
import { getResourceStats, listResources } from "@/lib/api/resources";
import type { Resource, ResourceStats } from "@/lib/types/resource";

const RECENT_LIMIT = 5;

export default function DashboardPage() {
  const router = useRouter();
  const [stats, setStats] = useState<ResourceStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);

  const [recent, setRecent] = useState<Resource[]>([]);
  const [recentLoading, setRecentLoading] = useState(true);
  const [recentError, setRecentError] = useState<string | null>(null);

  useEffect(() => {
    getResourceStats()
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setStatsLoading(false));
  }, []);

  function fetchRecent() {
    setRecentLoading(true);
    setRecentError(null);
    listResources({ limit: RECENT_LIMIT })
      .then((res) => setRecent(res.items))
      .catch((err) =>
        setRecentError(err instanceof ApiError ? err.message : "Failed to load resources.")
      )
      .finally(() => setRecentLoading(false));
  }

  useEffect(fetchRecent, []);

  return (
    <>
      <Topbar title="Dashboard" />
      <main className="mx-auto flex w-full max-w-6xl animate-fade-in flex-col gap-8 p-6 sm:p-8 lg:p-10">
        <PageHeader title="Dashboard" description="Your personal learning workspace." />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Total resources"
            value={stats?.total ?? 0}
            icon={IconLibrary}
            accent="indigo"
            loading={statsLoading}
          />
          <StatCard
            label="Articles"
            value={stats?.byType.article ?? 0}
            icon={IconArticle}
            accent="teal"
            loading={statsLoading}
          />
          <StatCard
            label="Videos"
            value={stats?.byType.video ?? 0}
            icon={IconVideo}
            accent="neutral"
            loading={statsLoading}
          />
          <StatCard
            label="Notes"
            value={stats?.byType.note ?? 0}
            icon={IconNote}
            accent="neutral"
            loading={statsLoading}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <div className="mb-4 flex items-center justify-between">
              <p className="text-sm font-medium text-content-primary">Recent resources</p>
              <Link href="/library" className="text-xs font-medium text-accent-indigo hover:underline">
                View all
              </Link>
            </div>
            <ResourceList
              resources={recent}
              loading={recentLoading}
              error={recentError}
              onRetry={fetchRecent}
              emptyDescription="Saved articles, videos, URLs, and notes will show up here."
              emptyAction={
                <Button size="sm" onClick={() => router.push("/library")}>
                  <IconPlus className="h-3.5 w-3.5" />
                  Add resource
                </Button>
              }
            />
          </Card>

          <Card>
            <p className="mb-4 text-sm font-medium text-content-primary">Continue learning</p>
            <ContinueLearningList />
          </Card>
        </div>
      </main>
    </>
  );
}
