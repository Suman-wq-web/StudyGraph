# Knowledge graph pipeline

> **Implemented (Phase 6), extended by Phase 7 recommendations (below).** See
> [ROADMAP.md](./ROADMAP.md) for what came before and what's still deferred (Phase 8 auth).

The knowledge graph is what turns a pile of saved resources into a map of what a user knows
and how it connects — the basis for the graph visualization and for learning recommendations.

## Pipeline stages

1. **Extract** (`app/services/ingestion/extraction.py`) — for each not-yet-extracted
   `document_chunk`, one Gemini call proposes candidate concepts and `(source, relation_type,
   target)` relationship triples, via the existing, **unmodified** Phase 5 `GenerationProvider`
   abstraction (`app/services/rag/generation.py`) — no new provider, no new SDK import site.
   The system prompt asks for a raw JSON object (`{"concepts": [...], "relationships": [...]}`)
   over the existing `stream_generate()` streaming interface, and the buffered response is
   parsed with `json.loads`. Gemini's native `response_schema`/JSON-mode would parse more
   reliably, but wiring it up would mean adding a method to `GenerationProvider` in
   `generation.py` — a file from the already-verified Phase 5 RAG chat pipeline that this phase
   deliberately leaves untouched. One retry with a stricter prompt on a malformed first
   response; a chunk that still doesn't parse is skipped (left for the next `/extract` call)
   rather than storing anything fabricated.
2. **Resolve** (`app/services/graph_extraction_service.py`) — candidate concept names are
   normalized (lowercased, whitespace-collapsed) and matched against a user's existing
   `concepts` by exact normalized-name match. A hit adds the new source resource id to the
   existing concept (idempotent — `$addToSet`); a miss creates a new concept. Embedding-
   similarity dedupe is a later refinement, not implemented here — two different phrasings of
   the same idea currently become two concepts unless their normalized names happen to match.
3. **Store** — resolved concepts upsert into the `concepts` collection
   (`app/db/concept_repository.py`); relationship triples upsert into `edges`
   (`app/db/edge_repository.py`) — a repeat triple strengthens `weight` and appends the new
   evidence chunk id rather than duplicating the edge; a repeat evidence chunk id is a no-op
   (see [DATABASE.md](./DATABASE.md) for both schemas). Each chunk is marked
   `concepts_extracted=true` once processed (whether or not it yielded any concepts), the same
   null-until-done idempotency signal Phase 4 uses for `DocumentChunk.embedding`.
4. **Build** (`app/services/graph/builder.py`) — on demand, a user's `concepts` + `edges` are
   loaded into an in-memory **NetworkX** `DiGraph` (nodes = concepts, edges carry
   `relation_type`/`weight`). The graph is rebuilt per request rather than kept resident,
   since it's derived data. An edge referencing a concept id that no longer exists is skipped
   rather than raising.
5. **Analyze** (`app/services/graph/traversal.py`) —
   - **Centrality**: betweenness centrality (pure Python, no extra dependency) identifies the
     most "load-bearing" concepts in a user's knowledge. NetworkX's `pagerank` was considered
     as a configurable alternative but requires numpy/scipy in this NetworkX version (its
     pure-Python fallback was removed), which nothing else in this codebase needs — dropped
     rather than adding a dependency for a non-default option.
   - **Traversal** over `prerequisite_of` edges (topological sort restricted to a target
     concept's ancestors) produces an ordered learning path; falls back to a non-topological
     but still complete ordering if the subgraph has a cycle (extraction has no
     cycle-prevention today).
6. **Visualize** — the graph is serialized to `{nodes, edges}` JSON via `GET /api/v1/graph`
   (`app/services/graph_service.py`, which also writes each node's freshly-computed
   `centrality_score` back onto its `concepts` document) and rendered client-side by
   `KnowledgeGraphView` using `react-force-graph-2d` — node size scales with centrality, edges
   are drawn directional with an arrowhead.

## Resource-level extraction status

Unlike Phase 3 (`/process`) and Phase 4 (`/embed`), triggering extraction does **not** change
`Resource.status` — there is no `extracting`/`extracted` value added to that enum. This was a
deliberate Phase 6 design choice: `Resource.status` is already a shared lifecycle three earlier
phases' services branch on, and extraction's progress is fully expressible as chunk counts
instead. `POST /api/v1/resources/{id}/extract` requires the resource to already be chunked
(`app/db/chunk_repository.py:count_by_resource` > 0) and returns immediately with how many
chunks are currently unextracted; `GET /api/v1/resources/{id}/extraction-status` reports
`extractedChunkCount`/`totalChunkCount`, the same shape as `processing-status`/
`embedding-status`. There is also no "already extracting" guard (unlike `/process`/`/embed`):
extraction's upserts are idempotent by construction (normalized concept name; `(source, target,
relation_type)` triple), so a duplicate trigger wastes some Gemini calls but cannot corrupt
stored data. See [API.md](./API.md#apiv1resourcesidextract-phase-6).

## Phase 7 — Recommendations

`GET /api/v1/recommendations` reuses the Phase 6 graph unmodified (`builder.build_user_graph`,
`traversal.compute_centrality`, both called but not changed) and ranks two deterministic v1
heuristics on top of it, in `app/services/graph/recommendations.py` — pure functions, no DB, no
HTTP, independently unit tested like `traversal.py`. Neither heuristic calls an LLM or invents
mastery/completion data the schema doesn't have; "coverage" is approximated by
`len(concept.source_resource_ids)`, a field `builder.py` already attaches to every node.

- **Gap** (`find_gaps`): ranks concepts by
  `prerequisite_of_out_degree * (1 + betweenness_centrality) / coverage` — concepts many
  others structurally depend on (they're the source of many `prerequisite_of` edges) but that
  are shallowly covered relative to that importance. A concept with no dependents is never a
  gap, regardless of coverage.
- **Next step** (`find_next_steps`): for every `prerequisite_of` edge (source → target) where
  the source is better-covered than the target, scores the target by
  `((source_coverage - target_coverage) / source_coverage) * (1 + source_centrality)` — "you
  cover X well; X is a prerequisite of Y; Y is still shallow; learn Y next." A target reachable
  from multiple qualifying prerequisites keeps only its best-scoring one.

`app/services/recommendation_service.py` orchestrates both (mirroring `graph_service.py`'s
shape), splits the requested `limit` roughly evenly between the two heuristics, and formats
each candidate's `reason` as a templated sentence built from the concrete numbers above — never
model-generated text, so the same graph always produces the same recommendations. It
deliberately does **not** call `concept_repository.set_centrality_scores` — that write-back
stays `graph_service.py`'s sole responsibility, so `/recommendations` never races `/graph` over
the same field. Empty `concepts`/`edges` returns `{"items": []}`, `200` — same empty-graph
contract as `GET /api/v1/graph`, never a `404`.

## Module map

| Concern | Module | Status |
|---|---|---|
| Concept/relation extraction | `app/services/ingestion/extraction.py` | **implemented** |
| Concept resolution/dedupe, pipeline orchestration | `app/services/graph_extraction_service.py` | **implemented** |
| `concepts`/`edges` persistence | `app/db/concept_repository.py`, `app/db/edge_repository.py` | **implemented** |
| Graph construction (NetworkX) | `app/services/graph/builder.py` | **implemented** |
| Centrality + learning-path traversal | `app/services/graph/traversal.py` | **implemented** |
| Recommendation heuristics (gap/next-step) | `app/services/graph/recommendations.py` | **implemented** (Phase 7) |
| Graph read orchestration | `app/services/graph_service.py` | **implemented** |
| Recommendation read orchestration | `app/services/recommendation_service.py` | **implemented** (Phase 7) |
| HTTP entry point (graph data) | `app/api/v1/graph.py` | **implemented** |
| HTTP entry point (extraction trigger/status) | `app/api/v1/resources.py` (`/extract`, `/extraction-status`) | **implemented** |
| HTTP entry point (recommendations) | `app/api/v1/recommendations.py` | **implemented** (Phase 7) |
| Visualization | `frontend/src/components/graph/KnowledgeGraphView.tsx` | **implemented** |
| Recommendations UI | `frontend/src/app/recommendations/page.tsx`, `frontend/src/components/recommendations/RecommendationCard.tsx` | **implemented** (Phase 7) |
