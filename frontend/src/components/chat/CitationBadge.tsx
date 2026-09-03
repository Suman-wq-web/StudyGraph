import Link from "next/link";
import type { Citation } from "@/lib/types/chat";
import type { ResourceType } from "@/lib/types/resource";
import { IconArticle, IconNote, IconUrl, IconVideo } from "@/components/ui/icons";

const TYPE_ICONS: Record<ResourceType, typeof IconArticle> = {
  article: IconArticle,
  video: IconVideo,
  url: IconUrl,
  note: IconNote,
};

/** Small reference chip linking an answer back to the source resource. */
export function CitationBadge({ citation }: { citation: Citation }) {
  const TypeIcon = TYPE_ICONS[citation.resourceType];
  return (
    <Link
      href={`/library?resource=${citation.resourceId}`}
      title={citation.snippet}
      className="inline-flex items-center gap-1 rounded-md bg-accent-teal/10 px-2 py-0.5 text-xs font-medium text-accent-teal transition-colors hover:bg-accent-teal/20"
    >
      <TypeIcon className="h-3 w-3 shrink-0" />
      {citation.resourceTitle}
    </Link>
  );
}
