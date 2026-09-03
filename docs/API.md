# API

The FastAPI backend exposes a single versioned REST API. The frontend is the only intended
consumer in Phase 1, but the contract is kept plain REST/JSON (plus SSE for streaming
answers) so it isn't frontend-specific.

## Conventions

- **Base path:** every route lives under `/api/v1`, aggregated in `backend/app/api/router.py`.
  A `/api/v2` could be added later without touching `v1`.
- **Liveness:** `GET /health` is unauthenticated and outside `/api/v1` — a plain check for the
  deployment platform, not part of the product API.
- **Auth:** none yet. Every `v1` route is unauthenticated and single-tenant for now; a
  `user_id` field and auth dependency are planned for Phase 8 without a schema migration to
  the request/response shape.
- **Errors:** not yet defined beyond FastAPI/Pydantic's default validation error shape
  (`{"detail": ...}`, `422` for validation, `404` for not-found). A consistent error envelope
  across all resources is deferred to a later phase.
- **Streaming:** `POST /api/v1/chat` streams tokens via Server-Sent Events rather than a single
  buffered response — see [`/api/v1/chat`](#apiv1chat-phase-5) below. A future frontend pass
  will consume this via the Vercel AI SDK for incremental rendering.

## Router map

| Prefix | Module | Purpose | Status |
|---|---|---|---|
| `/api/v1/resources` | `app/api/v1/resources.py` | Save/list/manage resources; trigger/observe chunking (Phase 3), embedding (Phase 4), and concept extraction (Phase 6) | **implemented** (Phase 2-4, 6) |
| `/api/v1/search` | `app/api/v1/search.py` | Semantic vector search over `document_chunks` | **implemented** (Phase 4) |
| `/api/v1/chat` | `app/api/v1/chat.py` | RAG query → streamed answer + citations | **implemented** (Phase 5) |
| `/api/v1/graph` | `app/api/v1/graph.py` | Knowledge graph nodes/edges for visualization | **implemented** (Phase 6) |
| `/api/v1/recommendations` | `app/api/v1/recommendations.py` | "What to learn next" suggestions (centrality/gap analysis) | **implemented** (Phase 7) |
| `/health` | `main.py` | Liveness check | **implemented** — returns `{"status": "ok"}` |

Each `v1` module is a real `APIRouter` already included in `app_router` (see
`app/api/router.py`), so adding the first real endpoint to any resource is a matter of adding
a route function to its module — no wiring changes needed elsewhere.

## `/api/v1/resources`

Request/response bodies are the Pydantic models in `backend/app/models/resource.py`, wire
format camelCase (`sourceUrl`, `createdAt`, ...). Full field-level schema:
[DATABASE.md](./DATABASE.md#resources).

| Method | Path | Body | Response | Notes |
|---|---|---|---|---|
| `POST` | `/api/v1/resources` | `ResourceCreate` | `201` + `Resource` | `status` always starts `pending` |
| `GET` | `/api/v1/resources` | — | `200` + `ResourceListResponse` | query params below |
| `GET` | `/api/v1/resources/stats` | — | `200` + `ResourceStats` | totals by `type` and `status` |
| `GET` | `/api/v1/resources/{id}` | — | `200` + `Resource`, or `404` | |
| `PATCH` | `/api/v1/resources/{id}` | `ResourceUpdate` (all fields optional) | `200` + `Resource`, or `404` | only fields present in the body are changed |
| `DELETE` | `/api/v1/resources/{id}` | — | `204`, or `404` | cascades: also deletes the resource's `document_chunks` |
| `POST` | `/api/v1/resources/{id}/process` | — | `202` + `Resource`, `404`, or `409` | starts/restarts chunking — see below |
| `GET` | `/api/v1/resources/{id}/processing-status` | — | `200` + `ProcessingStatusResponse`, or `404` | poll this for the chunking outcome |
| `POST` | `/api/v1/resources/{id}/embed` | — | `202` + `Resource`, `404`, or `409` | starts/restarts embedding — see below |
| `GET` | `/api/v1/resources/{id}/embedding-status` | — | `200` + `EmbeddingStatusResponse`, or `404` | poll this for the embedding outcome |
| `POST` | `/api/v1/resources/{id}/extract` | — | `202` + `ExtractionTriggerResponse`, `404`, or `409` | starts/restarts concept extraction — see below |
| `GET` | `/api/v1/resources/{id}/extraction-status` | — | `200` + `ExtractionStatusResponse`, or `404` | poll this for extraction progress |

`GET /api/v1/resources` query params (all optional): `type` (one of the `ResourceType` enum
values), `status` (one of the `ResourceStatus` enum values), `tag` (exact tag match), `search`
(case-insensitive substring match against `title`/`description`), `skip` (default `0`),
`limit` (default `20`, max `100`).

Validation errors (bad enum value, title too long, malformed `sourceUrl`, etc.) return `422`
with FastAPI/Pydantic's standard `{"detail": [...]}` shape. A resource ID that doesn't parse
as a MongoDB ObjectId is treated the same as one that doesn't exist — both return `404`, not
`422` — so callers don't need to special-case malformed IDs.

### `/api/v1/resources/{id}/process` (Phase 3)

Starts the document-processing pipeline (extract content → normalize → chunk with `tiktoken` →
write `document_chunks`) — see [DATABASE.md](./DATABASE.md#document_chunks) for the chunking
algorithm and [RAG.md](./RAG.md) for the full pipeline design. Full field-level schema:
[DATABASE.md](./DATABASE.md#resources).

- Returns **`202 Accepted`** immediately with the `Resource` at `status=processing` — the
  pipeline itself runs as a FastAPI `BackgroundTasks` job *after* the response is sent, so the
  request never blocks on tokenization or the Mongo writes. Poll
  `GET /{id}/processing-status` for the outcome (`ready` or `failed`).
  In tests, `TestClient` runs background tasks synchronously, so the outcome is already final
  by the time the `POST` call returns — see `backend/tests/test_processing.py`.
- Returns **`404`** if the resource doesn't exist (or the id doesn't parse as an ObjectId).
- Returns **`409 Conflict`** if the resource is already `status=processing` — this guards
  against a duplicate in-flight run from a double-click, not concurrent processing in general.
- **Idempotent:** re-processing (e.g. after editing a resource's content) replaces the
  resource's existing chunks rather than accumulating duplicates — see
  `app/db/chunk_repository.py:replace_chunks_for_resource`.
- On failure (no extractable content — e.g. a URL that fetches but has no readable text/no
  extractable PDF text, or a Video resource whose YouTube transcript couldn't be fetched — and
  no manually-provided `content` fallback either), the resource ends at `status=failed` with a
  short, user-safe `processing_error` — never a stack trace, and never fabricated content.
  Video resources (and URL resources whose `source_url` is a YouTube link) automatically fetch
  their transcript via `app/services/ingestion/youtube_transcript.py`; any other URL resource
  automatically fetches and extracts readable text via
  `app/services/ingestion/url_extraction.py` (HTML pages via `trafilatura`, direct PDF links via
  `pypdf`) — see [RAG.md](./RAG.md#pipeline-stages). Manually-provided `content` is used as a
  fallback if the automatic fetch fails in either case.

### `GET /api/v1/resources/{id}/processing-status` (Phase 3)

Response body — `ProcessingStatusResponse` (`app/models/processing.py`), camelCase on the wire:

| field | type | notes |
|---|---|---|
| `resourceId` | string | |
| `status` | enum | `pending` \| `processing` \| `ready` \| `embedding` \| `embedded` \| `failed` |
| `chunkCount` | int | live count from `document_chunks`, not denormalized/cached |
| `processingError` | string? | set only when `status=failed` |
| `updatedAt` | datetime | |

### `/api/v1/resources/{id}/embed` (Phase 4)

Embeds every not-yet-embedded chunk of an already-processed resource with the configured
embedding provider (**Gemini**, not OpenAI — see [RAG.md](./RAG.md)) and stores the vectors on
`document_chunks.embedding`. Full field-level schema:
[DATABASE.md](./DATABASE.md#document_chunks).

- Returns **`202 Accepted`** immediately with the `Resource` at `status=embedding` — the same
  background-task pattern as `/process`. Poll `GET /{id}/embedding-status` for the outcome.
- Returns **`404`** if the resource doesn't exist.
- Returns **`409 Conflict`** if the resource is already `status=embedding`, **or** if it hasn't
  been chunked yet (`status` isn't `ready`/`embedded`/`failed`, or it has zero chunks) — chunk
  first via `/process`.
- **Idempotent:** chunks that already have an embedding are skipped, so re-running this after a
  partial failure only embeds what's still missing — it never re-calls Gemini for unchanged
  chunks, and never accumulates duplicate embeddings (there's exactly one `embedding` field per
  chunk to begin with).
- Batches chunks (`EMBEDDING_BATCH_SIZE`, default 32) per Gemini call, and retries
  rate-limit/transient failures with exponential backoff (3 attempts) before giving up.
- On failure (misconfigured `GEMINI_API_KEY`, a non-retryable Gemini error, or retries
  exhausted), the resource ends at `status=failed` with a short, user-safe `processing_error` —
  never a raw exception message or any part of the API key.

### `GET /api/v1/resources/{id}/embedding-status` (Phase 4)

Response body — `EmbeddingStatusResponse` (`app/models/embedding.py`), camelCase on the wire:

| field | type | notes |
|---|---|---|
| `resourceId` | string | |
| `status` | enum | `pending` \| `processing` \| `ready` \| `embedding` \| `embedded` \| `failed` |
| `embeddedChunkCount` | int | live count of chunks with a non-null `embedding` |
| `totalChunkCount` | int | live count of all chunks for the resource |
| `processingError` | string? | set only when `status=failed` |
| `updatedAt` | datetime | |

### `/api/v1/resources/{id}/extract` (Phase 6)

Extracts candidate concepts and relationship triples from every not-yet-extracted chunk of an
already-processed resource, using the same Gemini `GenerationProvider` abstraction Phase 5 chat
uses (`app/services/rag/generation.py`, completely unmodified — see
[KNOWLEDGE_GRAPH.md](./KNOWLEDGE_GRAPH.md)), and upserts the results into `concepts`/`edges`.
Full pipeline design: [KNOWLEDGE_GRAPH.md](./KNOWLEDGE_GRAPH.md). Full field-level schema:
[DATABASE.md](./DATABASE.md#concepts).

- Returns **`202 Accepted`** immediately with an `ExtractionTriggerResponse` — the same
  background-task pattern as `/process`/`/embed`, except this endpoint does **not** change
  `Resource.status` (there is no `extracting`/`extracted` value; see
  [KNOWLEDGE_GRAPH.md](./KNOWLEDGE_GRAPH.md#resource-level-extraction-status) for why). Poll
  `GET /{id}/extraction-status` for progress.
- Returns **`404`** if the resource doesn't exist.
- Returns **`409 Conflict`** if the resource hasn't been chunked yet (zero chunks) — chunk
  first via `/process`. Unlike `/process`/`/embed`, there is **no** "already in progress" `409`
  guard — extraction's upserts are idempotent by construction (normalized concept name;
  `(source, target, relation_type)` triple), so a duplicate trigger wastes some Gemini calls
  but cannot corrupt stored data.
- **Idempotent:** chunks already marked `concepts_extracted` are skipped, so re-running this
  after a partial failure only processes what's still pending.
- A chunk whose Gemini response never parses as valid JSON (even after one stricter-prompt
  retry) is silently skipped — left `concepts_extracted=false` for a future `/extract` call —
  rather than failing the whole resource; a misconfigured/unavailable provider aborts the
  whole run the same way. Neither failure mode is recorded in a message field the way
  `/process`/`/embed` record `processing_error` — progress is only observable via
  `extraction-status`'s chunk counts staying behind `totalChunkCount`.

Response body — `ExtractionTriggerResponse` (`app/models/graph.py`), camelCase on the wire:

| field | type | notes |
|---|---|---|
| `resourceId` | string | |
| `chunksPending` | int | how many chunks were unextracted at trigger time |

### `GET /api/v1/resources/{id}/extraction-status` (Phase 6)

Response body — `ExtractionStatusResponse` (`app/models/graph.py`), camelCase on the wire:

| field | type | notes |
|---|---|---|
| `resourceId` | string | |
| `extractedChunkCount` | int | live count of chunks with `concepts_extracted=true` |
| `totalChunkCount` | int | live count of all chunks for the resource |
| `updatedAt` | datetime | the resource's own `updated_at` (not chunk-level) |

## `/api/v1/search`

### `POST /api/v1/search/vector` (Phase 4)

Embeds `query` with the configured embedding provider (Gemini, `RETRIEVAL_QUERY` task type) and
runs a **MongoDB Atlas Vector Search** (`$vectorSearch`) against `document_chunks.embedding`.
Read-only retrieval only — **no generated answer**; that's Phase 5's `POST /api/v1/chat`. Full
index/setup details: [DATABASE.md](./DATABASE.md#atlas-vector-search-setup).

Request body — `VectorSearchRequest` (`app/models/embedding.py`), camelCase on the wire:

| field | type | notes |
|---|---|---|
| `query` | string | required, 1-2000 chars |
| `topK` | int? | default `5`, 1-50 |
| `resourceType` | enum? | one of the `ResourceType` values; pre-filters to resources of that type |
| `tags` | string[]? | max 20; pre-filters to resources having any of these tags |

`resourceType`/`tags` are resolved to a `resource_id` allowlist first (via
`app/db/resource_repository.py:list_ids_by_filter`), then passed to `$vectorSearch` as a native
pre-filter on the chunk's `resource_id` field — not a post-hoc filter, so `topK` results are
still returned even with a filter applied (as long as enough matching chunks exist). If no
resource matches the filter, the endpoint returns an empty result immediately without calling
the embedding provider or Atlas.

Response body — `VectorSearchResponse`:

| field | type | notes |
|---|---|---|
| `query` | string | echoes the request |
| `results` | `VectorSearchResultItem[]` | see below |
| `count` | int | `results.length` |

Each `VectorSearchResultItem` carries enough metadata for future citation tracking (Phase 5):
`chunkId`, `resourceId`, `resourceTitle`, `resourceType`, `chunkIndex`, `text` (the full chunk
text, not just a snippet), and `score` (the Atlas `vectorSearchScore`, in `[0, 1]` for cosine
similarity — higher is more similar).

- Returns **`422`** for a validation error (empty/too-long `query`, `topK` out of range, invalid
  `resourceType`).
- Returns **`503 Service Unavailable`** if the query couldn't be embedded (provider
  misconfigured or erroring), or if `$vectorSearch` itself fails — most commonly because the
  database isn't a MongoDB Atlas cluster, or the `document_chunks_vector_index` hasn't been
  provisioned yet. This is the expected result of running against a local `mongod`, by design —
  see [DATABASE.md](./DATABASE.md#atlas-vector-search-setup).

## `/api/v1/chat`

### `POST /api/v1/chat` (Phase 5)

Retrieves relevant chunks via **hybrid retrieval** (Atlas Vector Search + Atlas Search BM25,
fused with reciprocal rank fusion — see [RAG.md](./RAG.md#why-hybrid-retrieval)), then streams a
**Gemini**-generated (`gemini-3.6-flash` by default), citation-grounded answer back as
**Server-Sent Events**. Unlike `/search/vector`, this endpoint generates an answer rather than
returning raw chunks.

Request body — `ChatQueryRequest` (`app/models/chat.py`), camelCase on the wire:

| field | type | notes |
|---|---|---|
| `query` | string | required, 1-2000 chars |
| `topK` | int? | default `8`, 1-20 — tighter than `/search/vector`'s 1-50 since this bounds how many chunks are stuffed into the LLM prompt |
| `resourceType` | enum? | one of the `ResourceType` values; pre-filters retrieval to resources of that type |
| `tags` | string[]? | max 20; pre-filters retrieval to resources having any of these tags |

`resourceType`/`tags` resolve to a `resource_id` allowlist (same mechanism as `/search/vector`)
applied as a native pre-filter to **both** the vector and BM25 retrievers.

Response: `200 OK`, `Content-Type: text/event-stream`, `Cache-Control: no-cache`. Body is a
sequence of SSE frames, always in this order:

1. Exactly one `citations` event — **always first**, even when `citations` is an empty array
   (zero retrieved chunks is not an error; the model is prompted to say it lacks relevant
   material rather than hallucinate). Data: `{"citations": Citation[]}`.
2. Zero or more `token` events, one per streamed answer delta, in generation order. Data:
   `{"delta": string}`.
3. Exactly one terminal event — `done` (`{"finishReason": string | null}`) on success, or
   `error` (`{"message": string}`) if generation failed after streaming had already started (see
   below).

Each `Citation` (`app/models/chat.py`), camelCase on the wire: `resourceId`, `resourceTitle`,
`resourceType`, `chunkId`, `chunkIndex`, `snippet` (truncated preview, `RAG_MAX_SNIPPET_CHARS`
chars, word-boundary-safe — the full chunk text is what actually goes into the prompt), `score`
(the chunk's fused reciprocal-rank-fusion score — unbounded, **not** a `[0,1]` similarity; higher
is more relevant). Citation order matches the LLM prompt's `[1]`/`[2]`/... numbering.

Example stream:

```
event: citations
data: {"citations":[{"resourceId":"...","resourceTitle":"...","resourceType":"note","chunkId":"...","chunkIndex":2,"snippet":"...","score":0.0164}]}

event: token
data: {"delta":"Gradient descent "}

event: token
data: {"delta":"is an optimization algorithm [1] that..."}

event: done
data: {"finishReason":"STOP"}
```

- Returns **`422`** for a validation error (empty/too-long `query`, `topK` out of range, invalid
  `resourceType`) — the response never opens an SSE stream in this case.
- Returns **`503 Service Unavailable`** (plain JSON `{"detail": ...}`, not SSE) if chat
  generation is misconfigured (e.g. missing `GEMINI_API_KEY`), the query couldn't be embedded, or
  **both** retrievers failed — all of this happens before the SSE response commits, so it can
  still be a normal HTTP error status. One retriever failing alone (e.g. the BM25 index isn't
  provisioned yet) does **not** 503 — retrieval degrades gracefully to the surviving retriever.
- A generation failure **after** streaming has already started (SSE headers sent, possibly some
  `token` events already delivered) cannot become an HTTP error status — it surfaces as a
  terminal `error` event instead, with `200` as the already-committed status code. This is a
  deliberate SSE trade-off, not a bug.

## `/api/v1/graph`

### `GET /api/v1/graph` (Phase 6)

Rebuilds the user's knowledge graph from `concepts`/`edges` on every call (NetworkX, in
process — no caching, no Atlas dependency; see [KNOWLEDGE_GRAPH.md](./KNOWLEDGE_GRAPH.md)),
computes centrality, writes each concept's freshly-computed `centrality_score` back to its
`concepts` document, and returns the serialized graph. No query params, no auth yet — single-
tenant, same as every other `v1` route.

Response body — `GraphResponse` (`app/models/graph.py`), camelCase on the wire:

| field | type | notes |
|---|---|---|
| `nodes` | `GraphNode[]` | `id`, `name`, `description`, `sourceResourceIds`, `centralityScore` (freshly computed, never `null` once there's at least one concept) |
| `edges` | `GraphEdgeResponse[]` | `id`, `source`/`target` (concept ids), `relationType`, `weight` |

No resources extracted yet (empty `concepts`/`edges`) returns `{"nodes": [], "edges": []}` —
not an error, and not a `404`.

## `/api/v1/recommendations`

### `GET /api/v1/recommendations` (Phase 7)

Rebuilds the user's knowledge graph the same way `GET /api/v1/graph` does (NetworkX, in
process, no caching), computes centrality, and ranks two deterministic v1 heuristics over it —
see [KNOWLEDGE_GRAPH.md](./KNOWLEDGE_GRAPH.md#phase-7-recommendations) for the exact scoring.
No LLM call, no auth yet — single-tenant, same as every other `v1` route. Optional query
param: `limit` (integer, `1`-`50`, default `10`) caps the total number of items returned,
split roughly evenly between the two heuristics.

Response body — `RecommendationResponse` (`app/models/recommendation.py`), camelCase on the
wire:

| field | type | notes |
|---|---|---|
| `items` | `Recommendation[]` | see below |

Each `Recommendation`:

| field | type | notes |
|---|---|---|
| `conceptId` | `string` | the recommended concept |
| `conceptName` | `string` | |
| `reasonType` | `"gap" \| "next_step"` | which heuristic produced this suggestion |
| `reason` | `string` | templated, numbers-backed sentence (not model-generated) |
| `score` | `number` | internal ranking score; heuristic-specific, not comparable across `reasonType` |
| `relatedConceptIds` | `string[]` | for `gap`: concepts that depend on this one; for `next_step`: the prerequisite concept it follows from |
| `sourceResourceIds` | `string[]` | resources the recommended concept was extracted from |

No concepts/edges yet (nothing extracted) returns `{"items": []}` — not an error, and not a
`404`.

## Request/response shapes

Defined as Pydantic models in `backend/app/models/*.py`, which double as the OpenAPI schema
FastAPI generates automatically at `/docs` (Swagger UI) and `/redoc` once the app is running.
The frontend's `lib/types/*.ts` mirror these by convention; there's no shared codegen yet
(worth revisiting once the contract stabilizes — see [ROADMAP.md](./ROADMAP.md)).

## CORS

Configured in `main.py` from `settings.allowed_origins_list`, which parses the
comma-separated `ALLOWED_ORIGINS` environment variable (see
[ENVIRONMENT.md](./ENVIRONMENT.md)). Locally this is the Next.js dev server origin; in
production it should be set to the deployed frontend's exact origin — never `*`.
