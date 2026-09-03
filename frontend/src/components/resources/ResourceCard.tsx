import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import {
  IconArticle,
  IconCalendar,
  IconEdit,
  IconNote,
  IconTrash,
  IconUrl,
  IconVideo,
} from "@/components/ui/icons";
import { RESOURCE_TYPE_LABELS, type Resource, type ResourceStatus, type ResourceType } from "@/lib/types/resource";

const TYPE_ICONS: Record<ResourceType, typeof IconArticle> = {
  article: IconArticle,
  video: IconVideo,
  url: IconUrl,
  note: IconNote,
};

const TYPE_TONES: Record<ResourceType, "indigo" | "teal" | "neutral"> = {
  article: "indigo",
  video: "teal",
  url: "neutral",
  note: "neutral",
};

const STATUS_TONES: Record<ResourceStatus, "neutral" | "indigo" | "teal" | "danger"> = {
  pending: "neutral",
  processing: "indigo",
  ready: "teal",
  embedding: "indigo",
  embedded: "teal",
  failed: "danger",
};

interface ResourceCardProps {
  resource: Resource;
  onSelect?: (resource: Resource) => void;
  onEdit?: (resource: Resource) => void;
  onDelete?: (resource: Resource) => void;
}

export function ResourceCard({ resource, onSelect, onEdit, onDelete }: ResourceCardProps) {
  const TypeIcon = TYPE_ICONS[resource.type];

  return (
    <Card
      interactive={Boolean(onSelect)}
      onClick={onSelect ? () => onSelect(resource) : undefined}
      onKeyDown={
        onSelect
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(resource);
              }
            }
          : undefined
      }
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      className="group"
    >
      <div className="flex items-start gap-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-base-elevated text-content-secondary">
          <TypeIcon className="h-[18px] w-[18px]" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={TYPE_TONES[resource.type]}>{RESOURCE_TYPE_LABELS[resource.type]}</Badge>
            <Badge tone={STATUS_TONES[resource.status]} className="capitalize">
              {resource.status}
            </Badge>
          </div>
          <p className="mt-1.5 truncate text-sm font-medium text-content-primary">
            {resource.title}
          </p>
          {resource.description && (
            <p className="mt-0.5 line-clamp-1 text-xs text-content-muted">
              {resource.description}
            </p>
          )}
          <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
            {resource.tags.slice(0, 4).map((tag) => (
              <span
                key={tag}
                className="rounded-full bg-base-elevated px-2 py-0.5 text-[11px] text-content-secondary"
              >
                {tag}
              </span>
            ))}
            {resource.tags.length > 4 && (
              <span className="text-[11px] text-content-muted">+{resource.tags.length - 4} more</span>
            )}
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-2">
          <span className="flex items-center gap-1 text-xs text-content-muted">
            <IconCalendar className="h-3.5 w-3.5" />
            {new Date(resource.createdAt).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
            })}
          </span>
          {(onEdit || onDelete) && (
            <div className="flex items-center gap-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
              {onEdit && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onEdit(resource);
                  }}
                  aria-label={`Edit ${resource.title}`}
                  className="flex h-7 w-7 items-center justify-center rounded-lg text-content-muted transition-colors hover:bg-base-elevated hover:text-accent-indigo"
                >
                  <IconEdit className="h-3.5 w-3.5" />
                </button>
              )}
              {onDelete && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(resource);
                  }}
                  aria-label={`Delete ${resource.title}`}
                  className="flex h-7 w-7 items-center justify-center rounded-lg text-content-muted transition-colors hover:bg-danger/10 hover:text-danger"
                >
                  <IconTrash className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
