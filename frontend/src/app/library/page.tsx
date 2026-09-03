"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { PageHeader } from "@/components/ui/PageHeader";
import { ResourceList } from "@/components/resources/ResourceList";
import { ResourceFormDialog } from "@/components/resources/ResourceFormDialog";
import { ResourceDetailDialog } from "@/components/resources/ResourceDetailDialog";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ToastStack } from "@/components/ui/Toast";
import { useToast } from "@/lib/hooks/useToast";
import {
  IconArticle,
  IconNote,
  IconPlus,
  IconSearch,
  IconUrl,
  IconVideo,
} from "@/components/ui/icons";
import { cn } from "@/lib/utils/cn";
import { ApiError } from "@/lib/api/client";
import {
  createResource,
  deleteResource,
  getResource,
  listResources,
  updateResource,
} from "@/lib/api/resources";
import {
  RESOURCE_TYPE_LABELS,
  RESOURCE_TYPES,
  type Resource,
  type ResourceCreateInput,
  type ResourceType,
  type ResourceUpdateInput,
} from "@/lib/types/resource";

const PAGE_SIZE = 20;

type TypeFilter = ResourceType | "all";

const TYPE_FILTER_ICONS: Record<ResourceType, typeof IconArticle> = {
  article: IconArticle,
  video: IconVideo,
  url: IconUrl,
  note: IconNote,
};

export default function LibraryPage() {
  return (
    <Suspense fallback={null}>
      <LibraryPageContent />
    </Suspense>
  );
}

/** Reads `?resource=` (useSearchParams needs a Suspense boundary above it in the app router). */
function LibraryPageContent() {
  const { toasts, push, dismiss } = useToast();
  const router = useRouter();
  const searchParams = useSearchParams();
  const resourceParam = searchParams.get("resource");

  const [resources, setResources] = useState<Resource[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [skip, setSkip] = useState(0);

  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<Resource | null>(null);
  const [viewing, setViewing] = useState<Resource | null>(null);
  const [deleting, setDeleting] = useState<Resource | null>(null);

  // Debounce free-text search so we don't fire a request per keystroke.
  useEffect(() => {
    const timeout = setTimeout(() => {
      setSkip(0);
      setSearch(searchInput.trim());
    }, 300);
    return () => clearTimeout(timeout);
  }, [searchInput]);

  const fetchResources = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await listResources({
        type: typeFilter === "all" ? undefined : typeFilter,
        search: search || undefined,
        skip,
        limit: PAGE_SIZE,
      });
      setResources((prev) => (skip === 0 ? response.items : [...prev, ...response.items]));
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load resources.");
    } finally {
      setLoading(false);
    }
  }, [typeFilter, search, skip]);

  useEffect(() => {
    fetchResources();
  }, [fetchResources]);

  // Opens a resource directly from a deep link (e.g. a chat citation ->
  // /library?resource={id}) via the same detail dialog used for a list click.
  useEffect(() => {
    if (!resourceParam) return;
    let cancelled = false;
    getResource(resourceParam)
      .then((resource) => {
        if (!cancelled) setViewing(resource);
      })
      .catch(() => {
        if (!cancelled) {
          push("Couldn't find that resource.", "error");
          router.replace("/library");
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resourceParam]);

  function handleTypeFilterChange(next: TypeFilter) {
    setTypeFilter(next);
    setSkip(0);
  }

  async function handleCreate(payload: ResourceCreateInput | ResourceUpdateInput) {
    const created = await createResource(payload as ResourceCreateInput);
    setAddOpen(false);
    setSkip(0);
    if (typeFilter === "all" || typeFilter === created.type) {
      setResources((prev) => [created, ...prev]);
    }
    setTotal((prev) => prev + 1);
    push(`"${created.title}" added to your library.`);
  }

  async function handleUpdate(payload: ResourceCreateInput | ResourceUpdateInput) {
    if (!editing) return;
    const updated = await updateResource(editing.id, payload as ResourceUpdateInput);
    setResources((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
    setEditing(null);
    setViewing((prev) => (prev && prev.id === updated.id ? updated : prev));
    push(`"${updated.title}" updated.`);
  }

  function handleProcessed(updated: Resource) {
    setResources((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
    setViewing((prev) => (prev && prev.id === updated.id ? updated : prev));
  }

  async function handleDelete() {
    if (!deleting) return;
    const title = deleting.title;
    try {
      await deleteResource(deleting.id);
      setResources((prev) => prev.filter((r) => r.id !== deleting.id));
      setTotal((prev) => Math.max(0, prev - 1));
      setViewing((prev) => (prev && prev.id === deleting.id ? null : prev));
      push(`"${title}" deleted.`);
    } catch (err) {
      push(err instanceof ApiError ? err.message : "Failed to delete resource.", "error");
    } finally {
      setDeleting(null);
    }
  }

  const hasMore = resources.length < total;
  const isFiltered = typeFilter !== "all" || search.length > 0;

  return (
    <>
      <Topbar title="Resource Library" />
      <main className="mx-auto flex w-full max-w-5xl animate-fade-in flex-col gap-6 p-6 sm:p-8 lg:p-10">
        <PageHeader
          title="Resource Library"
          description="All your saved articles, videos, URLs, and notes in one place."
          actions={
            <Button onClick={() => setAddOpen(true)}>
              <IconPlus className="h-4 w-4" />
              Add resource
            </Button>
          }
        />

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search your resources..."
            icon={<IconSearch className="h-4 w-4" />}
            className="sm:max-w-sm"
          />
          {!loading && !error && (
            <p className="text-xs text-content-muted">
              {total} resource{total === 1 ? "" : "s"}
            </p>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          {(["all", ...RESOURCE_TYPES] as TypeFilter[]).map((option) => {
            const OptionIcon = option === "all" ? null : TYPE_FILTER_ICONS[option];
            return (
              <button
                key={option}
                onClick={() => handleTypeFilterChange(option)}
                className={cn(
                  "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                  typeFilter === option
                    ? "border-accent-indigo/40 bg-accent-indigo/10 text-accent-indigo"
                    : "border-base-border text-content-secondary hover:border-accent-teal/50 hover:text-content-primary"
                )}
              >
                {OptionIcon && <OptionIcon className="h-3.5 w-3.5" />}
                {option === "all" ? "All" : RESOURCE_TYPE_LABELS[option]}
              </button>
            );
          })}
        </div>

        <ResourceList
          resources={resources}
          loading={loading && skip === 0}
          error={error}
          onRetry={fetchResources}
          onSelect={setViewing}
          onEdit={setEditing}
          onDelete={setDeleting}
          emptyTitle={isFiltered ? "No matching resources" : "No resources yet"}
          emptyDescription={
            isFiltered
              ? "Try a different search term or clear the type filter."
              : "Save your first article, video, URL, or note to get started."
          }
          emptyAction={
            !isFiltered && (
              <Button size="sm" onClick={() => setAddOpen(true)}>
                <IconPlus className="h-3.5 w-3.5" />
                Add resource
              </Button>
            )
          }
        />

        {!loading && !error && hasMore && (
          <div className="flex justify-center pt-2">
            <Button variant="secondary" onClick={() => setSkip((prev) => prev + PAGE_SIZE)}>
              Load more
            </Button>
          </div>
        )}
      </main>

      {addOpen && <ResourceFormDialog onClose={() => setAddOpen(false)} onSubmit={handleCreate} />}

      {editing && (
        <ResourceFormDialog
          resource={editing}
          onClose={() => setEditing(null)}
          onSubmit={handleUpdate}
        />
      )}

      {viewing && (
        <ResourceDetailDialog
          resource={viewing}
          onClose={() => {
            setViewing(null);
            if (searchParams.get("resource")) router.replace("/library");
          }}
          onEdit={() => {
            setEditing(viewing);
            setViewing(null);
          }}
          onDelete={() => setDeleting(viewing)}
          onProcessed={handleProcessed}
        />
      )}

      {deleting && (
        <ConfirmDialog
          title="Delete resource"
          description={`Delete "${deleting.title}"? This can't be undone.`}
          confirmLabel="Delete"
          onCancel={() => setDeleting(null)}
          onConfirm={handleDelete}
        />
      )}

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </>
  );
}
