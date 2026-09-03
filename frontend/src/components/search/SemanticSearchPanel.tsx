"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { IconSearch, IconSparkles } from "@/components/ui/icons";
import { ApiError } from "@/lib/api/client";
import { vectorSearch } from "@/lib/api/search";
import { RESOURCE_TYPE_LABELS } from "@/lib/types/resource";
import type { VectorSearchResultItem } from "@/lib/types/search";

/**
 * Raw semantic-retrieval preview for Phase 4: embeds the query with Gemini,
 * runs MongoDB Atlas Vector Search, and shows the matching chunks with their
 * similarity score. Deliberately not a chat interface -- no generated
 * answer, no citations UI beyond the raw resource/chunk identifiers. That's
 * Phase 5.
 */
export function SemanticSearchPanel() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<VectorSearchResultItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    try {
      const response = await vectorSearch({ query: query.trim(), topK: 5 });
      setResults(response.results);
    } catch (err) {
      setResults(null);
      setError(
        err instanceof ApiError
          ? err.message
          : "Search failed. Is the backend running and configured with a Gemini API key?"
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-base-border bg-base-surface/60 p-4">
      <div className="flex items-center gap-2">
        <IconSparkles className="h-4 w-4 text-accent-teal" />
        <p className="text-sm font-medium text-content-primary">Semantic search (preview)</p>
      </div>
      <p className="text-xs text-content-muted">
        Searches your embedded resources by meaning, not keywords. Shows raw retrieval
        results only -- generated answers with citations arrive in a later phase.
      </p>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. how does gradient descent work?"
          icon={<IconSearch className="h-4 w-4" />}
          className="flex-1"
        />
        <Button type="submit" loading={loading} disabled={!query.trim()}>
          Search
        </Button>
      </form>

      <div className="min-h-[80px]">
        {loading && <LoadingState message="Searching..." />}

        {!loading && error && <ErrorState message={error} />}

        {!loading && !error && results !== null && results.length === 0 && (
          <EmptyState
            icon={<IconSearch className="h-5 w-5" />}
            title="No matches found"
            description="Try a different phrasing, or make sure at least one resource has been processed and embedded."
          />
        )}

        {!loading && !error && results && results.length > 0 && (
          <ul className="flex flex-col gap-2">
            {results.map((result) => (
              <li
                key={result.chunkId}
                className="rounded-xl border border-base-border bg-base px-3.5 py-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <Badge tone="indigo">{RESOURCE_TYPE_LABELS[result.resourceType]}</Badge>
                    <span className="text-xs font-medium text-content-primary">
                      {result.resourceTitle}
                    </span>
                  </div>
                  <span className="text-xs font-medium text-accent-teal">
                    {(result.score * 100).toFixed(1)}% match
                  </span>
                </div>
                <p className="mt-1.5 line-clamp-3 text-xs leading-relaxed text-content-secondary">
                  {result.text}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
