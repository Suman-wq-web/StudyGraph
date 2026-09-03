"use client";

import { useEffect, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { PageHeader } from "@/components/ui/PageHeader";
import { KnowledgeGraphView } from "@/components/graph/KnowledgeGraphView";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { IconGraph } from "@/components/ui/icons";
import { ApiError } from "@/lib/api/client";
import { getKnowledgeGraph } from "@/lib/api/graph";
import type { GraphNode, GraphResponse } from "@/lib/types/graph";

export default function GraphPage() {
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getKnowledgeGraph()
      .then((data) => {
        if (!cancelled) setGraph(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load the graph.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <Topbar title="Knowledge Graph" />
      <main className="mx-auto flex w-full max-w-6xl animate-fade-in flex-col gap-6 p-6 sm:p-8 lg:p-10">
        <PageHeader
          title="Knowledge Graph"
          description="An explorable map of the concepts extracted from your saved resources, and how they connect."
          actions={graph ? <Badge tone="indigo">{graph.nodes.length} concepts</Badge> : undefined}
        />

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_300px]">
          <Card className="flex min-h-[440px] items-center justify-center p-0">
            {loading && <LoadingState message="Loading your knowledge graph..." />}
            {!loading && error && (
              <ErrorState
                message={error}
                onRetry={() => {
                  setLoading(true);
                  setError(null);
                  getKnowledgeGraph()
                    .then(setGraph)
                    .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load the graph."))
                    .finally(() => setLoading(false));
                }}
              />
            )}
            {!loading && !error && (
              <KnowledgeGraphView data={graph ?? undefined} onNodeClick={setSelected} />
            )}
          </Card>

          <Card className="flex flex-col gap-3">
            <div className="flex items-center gap-2 text-content-secondary">
              <IconGraph className="h-4 w-4" />
              <p className="text-sm font-medium text-content-primary">Selected concept</p>
            </div>
            {selected ? (
              <div className="flex flex-col gap-2">
                <p className="text-sm font-semibold text-content-primary">{selected.name}</p>
                {selected.description && (
                  <p className="text-xs leading-relaxed text-content-secondary">{selected.description}</p>
                )}
                <p className="text-xs text-content-muted">
                  From {selected.sourceResourceIds.length} resource
                  {selected.sourceResourceIds.length === 1 ? "" : "s"}
                </p>
                {selected.centralityScore !== null && (
                  <p className="text-xs text-content-muted">
                    Centrality: {selected.centralityScore.toFixed(3)}
                  </p>
                )}
              </div>
            ) : (
              <p className="text-xs leading-relaxed text-content-muted">
                Click a node in the graph to see its details, source resources, and connections
                here.
              </p>
            )}
          </Card>
        </div>
      </main>
    </>
  );
}
