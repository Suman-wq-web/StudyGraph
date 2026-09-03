"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { IconGraph } from "@/components/ui/icons";
import type { GraphNode, GraphResponse } from "@/lib/types/graph";

// react-force-graph-2d renders to <canvas> and touches `window`, so it must
// be loaded client-side only.
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

interface RenderNode {
  id: string;
  name: string;
  centralityScore: number | null;
}

interface RenderLink {
  id: string;
  source: string;
  target: string;
  relationType: string;
  weight: number;
}

interface KnowledgeGraphViewProps {
  data?: GraphResponse;
  /** Bubbles the clicked node's full data up so a host page can render a
   * details panel (see app/graph/page.tsx). */
  onNodeClick?: (node: GraphNode) => void;
}

/** Reads the app's theme tokens once at mount so the canvas (which can't
 * use CSS `var()`) still matches the current light/dark palette -- see
 * app/globals.css. Falls back to the light-theme values during SSR/before
 * mount. */
function useThemeColors() {
  const [colors, setColors] = useState({
    indigo: "#4f46e5",
    teal: "#0d9488",
    muted: "#8892a0",
  });

  useEffect(() => {
    const style = getComputedStyle(document.documentElement);
    const read = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
    setColors({
      indigo: read("--color-accent-indigo", "#4f46e5"),
      teal: read("--color-accent-teal", "#0d9488"),
      muted: read("--color-content-muted", "#8892a0"),
    });
  }, []);

  return colors;
}

/** Knowledge graph canvas (Phase 6): renders an empty state until
 * concepts/edges exist, otherwise a force-directed graph via
 * react-force-graph-2d -- node size scales with centrality, edges are
 * directional (source is a prerequisite/relation of target). */
export function KnowledgeGraphView({ data, onNodeClick }: KnowledgeGraphViewProps) {
  const colors = useThemeColors();

  const graphData = useMemo(() => {
    if (!data) return { nodes: [] as RenderNode[], links: [] as RenderLink[] };
    return {
      nodes: data.nodes.map(
        (node): RenderNode => ({
          id: node.id,
          name: node.name,
          centralityScore: node.centralityScore,
        })
      ),
      links: data.edges.map(
        (edge): RenderLink => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          relationType: edge.relationType,
          weight: edge.weight,
        })
      ),
    };
  }, [data]);

  if (!data || data.nodes.length === 0) {
    return (
      <EmptyState
        icon={<IconGraph className="h-5 w-5" />}
        title="Your knowledge graph is empty"
        description="Once concepts are extracted from your saved resources, they'll appear here as an explorable graph."
      />
    );
  }

  const maxCentrality = Math.max(0.0001, ...graphData.nodes.map((node) => node.centralityScore ?? 0));

  return (
    <div className="h-[440px] w-full overflow-hidden rounded-xl">
      <ForceGraph2D
        graphData={graphData}
        nodeId="id"
        nodeLabel="name"
        // `next/dynamic` erases react-force-graph-2d's generic NodeType/LinkType
        // params, so its accessor props type as the library's own loose
        // NodeObject<{}>/LinkObject<{}> shape rather than RenderNode/RenderLink
        // -- narrowed with `as` at each callback boundary instead.
        nodeVal={(node: unknown) => {
          const { centralityScore } = node as RenderNode;
          return 3 + 9 * ((centralityScore ?? 0) / maxCentrality);
        }}
        nodeColor={() => colors.indigo}
        linkLabel={(link: unknown) => (link as RenderLink).relationType.replace(/_/g, " ")}
        linkColor={() => colors.muted}
        linkWidth={(link: unknown) => 1 + Math.min((link as RenderLink).weight, 5) / 2}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={1}
        linkDirectionalArrowColor={() => colors.muted}
        onNodeClick={(node: unknown) => {
          const { id } = node as RenderNode;
          const original = data.nodes.find((candidate) => candidate.id === id);
          if (original) onNodeClick?.(original);
        }}
        cooldownTicks={100}
      />
    </div>
  );
}
