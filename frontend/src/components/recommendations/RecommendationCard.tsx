import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { Recommendation } from "@/lib/types/recommendation";

const REASON_LABEL: Record<Recommendation["reasonType"], string> = {
  gap: "Coverage gap",
  next_step: "Next step",
};

interface RecommendationCardProps {
  recommendation: Recommendation;
}

/** "Learn next" suggestion, deterministically derived from the knowledge
 * graph (see backend/app/services/graph/recommendations.py) -- no
 * model-generated text, `reason` is a templated, numbers-backed sentence. */
export function RecommendationCard({ recommendation }: RecommendationCardProps) {
  const { conceptName, reasonType, reason, sourceResourceIds } = recommendation;

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-content-primary">{conceptName}</p>
        <Badge tone={reasonType === "gap" ? "indigo" : "teal"}>{REASON_LABEL[reasonType]}</Badge>
      </div>
      <p className="mt-1 text-xs text-content-muted">{reason}</p>
      <p className="mt-2 text-[11px] text-content-muted">
        From {sourceResourceIds.length} resource{sourceResourceIds.length === 1 ? "" : "s"}
      </p>
    </Card>
  );
}
