# Roadmap

Phased plan from this scaffold to a working product. Each phase should end with something
runnable and tested before the next one starts.

## Phase 1 — Foundation

- [x] Repository structure: `frontend/`, `backend/`, `docs/`.
- [x] Frontend: Next.js App Router shell (Dashboard, Library, Knowledge Graph, AI Assistant,
      Recommendations, Settings), responsive sidebar navigation, light/dark theming, a small
      `ui/` primitives layer, typed API client stubs.
- [x] Backend: FastAPI entrypoint, environment-based config, isolated MongoDB access module,
      versioned router structure, Pydantic models for all four collections, `/health`
      endpoint, service-layer boundaries for ingestion/RAG/graph (all stubs).
- [x] Documentation set (this `docs/` folder).
- [ ] No AI, RAG, embeddings, vector search, extraction, or graph logic — intentionally.

## Phase 2 — Resource ingestion

- [x] `POST /api/v1/resources`, `GET /api/v1/resources` (filter by `type`/`status`/`tag`,
      search `title`/`description`, pagination), `GET /api/v1/resources/{id}`,
      `PATCH /api/v1/resources/{id}` (partial update), `DELETE /api/v1/resources/{id}`, and
      `GET /api/v1/resources/stats`. See [API.md](./API.md#apiv1resources).
- [x] Repository layer (`app/db/resource_repository.py`) and service layer
      (`app/services/resource_service.py`) between the routes and MongoDB.
- [x] Pydantic request/response validation (`app/models/resource.py`): title/tag/URL rules,
      camelCase wire format, partial-update semantics via `exclude_unset`.
- [x] Frontend Library page wired to the real API: search (debounced), type filtering,
      add/edit resource forms, a resource detail view, delete with confirmation, and
      loading/empty/error states (`ResourceList`, `ResourceFormDialog`,
      `ResourceDetailDialog`).
- [x] Backend tests: create, list (filters/search/pagination), get, update, delete, and
      validation-error cases (`backend/tests/test_resources.py`).
- [x] Text extraction per resource type (article/webpage scraping) — Phase 2 originally accepted
      `content` as-is (typed/pasted text or a plain note) rather than fetching and extracting it
      server-side; automatic extraction was later added on top of the Phase 3 pipeline for both
      Video (YouTube transcript) and URL (YouTube transcript, or generic HTML/PDF extraction) —
      see that phase's content-extraction bullet below.

## Phase 3 — Document processing and chunking

- [x] `POST /api/v1/resources/{id}/process` (starts/restarts the pipeline, runs as a FastAPI
      `BackgroundTasks` job so the request returns immediately with `status=processing`) and
      `GET /api/v1/resources/{id}/processing-status` (poll for the outcome + live chunk count).
      See [API.md](./API.md#apiv1resourcesidprocess-phase-3).
- [x] Content extraction per resource type (`app/services/ingestion/content_extraction.py`):
      Note/Article use `resource.content` as-is, falling back to a clear, honest
      `processing_error` rather than fabricating text when it's missing. Video automatically
      fetches its transcript from a YouTube `source_url`
      (`app/services/ingestion/youtube_transcript.py`, added after Phase 3 shipped). URL
      resources automatically fetch their content too (added later still): a YouTube link uses
      the same transcript fetch as Video; any other link is fetched and its readable text
      extracted via `app/services/ingestion/url_extraction.py` -- HTML pages via `trafilatura`
      (script/nav/style noise stripped, headings/paragraphs kept), direct PDF URLs via `pypdf`
      (page text extracted; a scanned/image-only PDF with no text layer is reported as a clear
      error, not silently empty -- OCR is out of scope). `url_extraction.py` includes a basic
      SSRF guard (http(s)-only, rejects localhost/private/link-local/reserved/multicast
      addresses for both literal IPs and resolved hostnames, re-validates every redirect hop
      rather than following redirects blindly) plus a response size cap and timeout, both
      configurable (`URL_FETCH_TIMEOUT_SECONDS`/`URL_FETCH_MAX_BYTES` — see
      [ENVIRONMENT.md](./ENVIRONMENT.md)). Every one of these fetches falls back to
      manually-provided `content` if it fails, and otherwise surfaces the fetch failure as a
      clear `processing_error`.
- [x] Text normalization (`app/services/ingestion/normalization.py`): collapses excess blank
      lines/trailing whitespace from pasted content without altering wording.
- [x] Token-aware chunking with `tiktoken` (`app/services/ingestion/chunking.py`): 512-token
      chunks with a 64-token overlap by default, both configurable via `app/config.py`
      (`chunk_size_tokens`/`chunk_overlap_tokens`) rather than hard-coded. Pure, deterministic,
      unit-tested independently of Mongo/FastAPI — see
      `backend/tests/test_chunking.py`.
- [x] `document_chunks` persistence (`app/db/chunk_repository.py`): idempotent
      re-processing — each run replaces a resource's existing chunks rather than accumulating
      duplicates. Deleting a resource cascades to delete its chunks.
- [x] Processing lifecycle on `Resource.status` (`pending → processing → ready | failed`) plus
      a new `Resource.processing_error` field for a user-safe failure message. See
      [DATABASE.md](./DATABASE.md#resources).
- [x] Minimal frontend surface: the resource detail view shows processing status, a
      trigger/reprocess button, a polled in-progress state, the resulting chunk count, and a
      failure message — no new pages, no AI UI.
- [x] Tests: chunking (empty/short/at-boundary/large/overlap/ordering/determinism/no-empty-
      chunks), normalization, content extraction per resource type, generic URL fetch/extraction
      (SSRF guard, content-type detection, HTML noise removal, PDF text/scanned-PDF handling,
      redirects, failures — `backend/tests/test_url_extraction.py`, mocked `httpx` transport, no
      real network), and processing API/service tests (idempotency, cascade delete, 404s, the
      already-processing guard).
- [ ] Embeddings are explicitly **not** written here — `DocumentChunk.embedding` stays `null`
      until Phase 4.

## Phase 4 — Embeddings + MongoDB Atlas Vector Search

- [x] **Gemini, not OpenAI, is the embedding provider** — a deliberate change from the original
      plan, to use Google's free tier and minimize API cost. `EMBEDDING_PROVIDER`,
      `GEMINI_API_KEY`, `GEMINI_EMBEDDING_MODEL` (default `gemini-embedding-001`), and
      `GEMINI_EMBEDDING_DIMENSIONS` are all configurable; nothing calls the OpenAI API. See
      [RAG.md](./RAG.md) ("Embedding provider abstraction").
- [x] `EmbeddingProvider` abstraction (`app/services/rag/embeddings.py`) with
      `GeminiEmbeddingProvider` as its only implementation — the current, non-deprecated
      `google-genai` SDK, not `google-generativeai`. Embedding dimension is read off the actual
      API response, never hard-coded.
- [x] `POST /api/v1/resources/{id}/embed` and `GET /api/v1/resources/{id}/embedding-status`
      (`app/services/embedding_service.py`): batched, retried (exponential backoff on
      rate-limit/transient errors), idempotent (skips already-embedded chunks), never stores a
      partial/invalid vector. Extends `Resource.status` with `embedding`/`embedded` without
      breaking the Phase 3 `pending`/`processing`/`ready`/`failed` transitions. See
      [API.md](./API.md#apiv1resourcesidembed-phase-4).
- [x] MongoDB **Atlas Vector Search** index (`document_chunks_vector_index`) documented —
      name, dimensions, similarity metric, vector field, filter fields, and exact Atlas setup
      steps — in [DATABASE.md](./DATABASE.md#atlas-vector-search-setup). Not auto-provisioned
      (same deferred-to-Phase-8 status as the standard indexes); requires a real Atlas cluster,
      which a local `mongod` cannot substitute for.
- [x] `POST /api/v1/search/vector` (`app/services/search_service.py`,
      `app/db/chunk_repository.py:vector_search`): embeds the query, runs `$vectorSearch`,
      optionally pre-filters by resource type/tags, returns raw retrieved chunks + resource
      metadata (no generated answer). See [API.md](./API.md#apiv1searchvector-phase-4).
- [x] Minimal frontend surface: the resource detail view's embedding panel (trigger, in
      progress, embedded chunk count, failure message), and a real (not fake) semantic-search
      preview panel on `/chat`, above the still-placeholder `ChatPanel`.
- [x] Tests: `EmbeddingProvider`/Gemini provider (mocked SDK client — no real API calls in
      normal runs), embedding pipeline (batching, retry, idempotency, partial-failure handling,
      cascade delete), and search request validation/metadata filtering/response shape (mocked
      `vector_search` — no real Atlas dependency). Opt-in, credential-gated integration tests
      (`test_gemini_integration.py`, `test_atlas_integration.py`) exist for real end-to-end
      verification but are skipped by default.
- [ ] **BM25 and hybrid retrieval fusion are explicitly deferred to Phase 5** (see below) — this
      phase ships semantic (vector-only) retrieval on its own, which is already useful for the
      search preview; combining it with keyword search matters most once RAG chat needs
      retrieval quality to matter for an answer.

## Phase 5 — RAG chat (backend)

- [x] Atlas Search (BM25 full-text) fused with the Phase 4 vector search into true hybrid
      retrieval (`app/services/rag/retrieval.py:hybrid_search`/`hybrid_search_with_scores`) via
      reciprocal rank fusion (`RAG_RRF_K`, default `60`) — see [RAG.md](./RAG.md) ("Why hybrid
      retrieval"). A single retriever failing (e.g. an index not yet provisioned) degrades
      gracefully to the other rather than failing the whole request; both failing raises
      `RetrievalUnavailableError`.
- [x] `app/services/rag/citations.py` (chunk → resource join, truncated snippet, fused-rank
      order) and `app/services/rag/pipeline.py` (retrieval → citations → prompt → generation
      orchestration).
- [x] `app/services/rag/generation.py`: `GenerationProvider` abstraction +
      `GeminiGenerationProvider` (`gemini-3.6-flash` by default, `GEMINI_CHAT_MODEL`) — mirrors
      the Phase 4 embedding provider abstraction; reuses the same `GEMINI_API_KEY` and
      `google.genai` SDK client, calling `generate_content_stream` instead of `embed_content`.
- [x] `POST /api/v1/chat` streaming via Server-Sent Events (`citations` event first, then
      `token` events, then a terminal `done`/`error` event) — see
      [API.md](./API.md#apiv1chat-phase-5).
- [x] MongoDB Atlas Search (BM25) index (`document_chunks_text_search`) documented — name,
      field, filter field, and exact index definition — in
      [DATABASE.md](./DATABASE.md#atlas-search-bm25-setup). Not auto-provisioned, same
      deferred-to-Phase-8 status as the other indexes.
- [x] Tests: hybrid retrieval fusion/filtering/partial-failure handling, citation
      assembly/snippet truncation, the generation provider (mocked SDK client), the
      streaming pipeline (event ordering, retry-then-error semantics), and the `/chat` API
      (validation, `503` unavailability, SSE happy path/mid-stream error) — all mocked, no real
      Gemini/Atlas dependency. Opt-in, credential-gated integration tests
      (`test_gemini_chat_integration.py`, `test_rag_chat_integration.py`) exist for real
      end-to-end verification but are skipped by default.
- [ ] Wire the frontend `ChatPanel` to the Vercel AI SDK for streamed rendering, with
      `CitationBadge`s linking back to resources — deferred to a separate frontend pass; the
      backend API is ready for it.

## Phase 6 — Knowledge graph

- [x] Concept/relationship extraction (`app/services/ingestion/extraction.py`): one Gemini
      call per chunk via the existing, **unmodified** Phase 5 `GenerationProvider`
      (`app/services/rag/generation.py`) -- no new provider, no new SDK import site. Prompts
      for raw JSON over the existing `stream_generate()` interface (Gemini's native
      `response_schema` mode was deliberately not used, since wiring it up would require
      touching the already-verified Phase 5 file); one retry with a stricter prompt on a
      malformed first response, then the chunk is skipped rather than storing anything
      fabricated. See [KNOWLEDGE_GRAPH.md](./KNOWLEDGE_GRAPH.md).
- [x] Concept resolution/dedupe (`app/services/graph_extraction_service.py`): exact
      normalized-name match against a user's existing `concepts` first; a miss creates a new
      concept, a hit adds the new source resource id. Embedding-similarity dedupe remains a
      later refinement, not implemented here.
- [x] `concepts`/`edges` persistence (`app/db/concept_repository.py`,
      `app/db/edge_repository.py`) -- idempotent upserts: a repeat concept name adds a source
      resource id rather than duplicating, a repeat relationship triple strengthens `weight`
      and appends evidence rather than duplicating the edge.
- [x] `POST /api/v1/resources/{id}/extract` and `GET /api/v1/resources/{id}/extraction-status`
      -- same background-task pattern as `/process`/`/embed`, but with no `Resource.status`
      change: extraction progress is entirely visible via chunk counts
      (`DocumentChunk.concepts_extracted`), a deliberate choice to avoid touching the
      Phase 3/4 status lifecycle. See [API.md](./API.md#apiv1resourcesidextract-phase-6).
- [x] Graph construction (`app/services/graph/builder.py`): on-demand NetworkX `DiGraph` from
      a user's `concepts`/`edges`, rebuilt fresh per request.
- [x] Analysis (`app/services/graph/traversal.py`): betweenness centrality, and
      `prerequisite_of`-only traversal for ordered learning paths -- the basis for Phase 7.
- [x] `GET /api/v1/graph` (`app/services/graph_service.py`); `KnowledgeGraphView` renders real
      data with `react-force-graph-2d`, node size by centrality; the resource detail view gets
      a minimal extraction trigger/status panel, matching the Phase 3/4 pattern.
- [x] Tests: extraction JSON parsing/retry/error-propagation (mocked provider), concept/edge
      repository upsert semantics, graph builder/traversal (pure, fixture-based), the
      extraction pipeline (dedupe across chunks, idempotent re-extraction, partial-failure
      handling), and `GET /api/v1/graph` -- all against local Mongo, no Atlas dependency (no
      vector/text search is involved in this phase at all).

## Phase 7 — Recommendations (current)

- [x] `GET /api/v1/recommendations` (`app/api/v1/recommendations.py`,
      `app/services/recommendation_service.py`): deterministic v1 heuristics over the Phase 6
      graph — no LLM call, no new collections/fields/indexes, no mastery/completion data (the
      schema has none). Two ranked recommendation types, both pure functions in
      `app/services/graph/recommendations.py` operating on the same `nx.DiGraph` +
      centrality dict `builder.py`/`traversal.py` already produce:
      - **Gap**: a concept many others structurally depend on (`prerequisite_of` out-degree)
        but with shallow source coverage relative to that importance.
      - **Next step**: a concept one `prerequisite_of` hop from something already
        well-covered, itself still shallow.
      "Coverage" is approximated by `len(concept.source_resource_ids)`, a field already on
      every graph node — no new field was added. See
      [KNOWLEDGE_GRAPH.md](./KNOWLEDGE_GRAPH.md#phase-7-recommendations).
- [x] Response `reason` text is a templated sentence built from concrete numbers
      (dependent/coverage counts), not model-generated — deterministic and explainable by
      construction, never re-runs differently for the same graph.
      Empty `concepts`/`edges` returns `{"items": []}`, `200`, matching `GET /api/v1/graph`'s
      empty-graph contract rather than a `404`.
- [x] Frontend Recommendations page wired to real data (`getRecommendations` in
      `lib/api/recommendations.ts`): loading/empty/error/populated states matching `/graph`'s
      pattern, `RecommendationCard` showing the concept, a gap/next-step badge, the reason
      sentence, and source resource count.
- [x] Tests: `app/services/graph/recommendations.py` unit tested pure/fixture-based (no DB, no
      FastAPI — mirrors `test_graph_traversal.py`), and `GET /api/v1/recommendations` tested
      against real local Mongo via the same extract-then-read pattern as `test_graph_api.py`
      (`backend/tests/test_recommendation_algorithm.py`,
      `backend/tests/test_recommendations_api.py`).
- [ ] Resource-level (rather than concept-level) recommendations, and any
      embedding/LLM-assisted scoring refinement, remain a later revisit — not implemented
      here, same "later refinement" framing Phase 6 used for embedding-similarity dedupe.

## Phase 8 — Auth, multi-user hardening, polish

- Real authentication. `resources` and `document_chunks` both gain a `user_id` field at this
  point (deliberately deferred until now — see [DATABASE.md](./DATABASE.md)) and every
  repository query gets a `user_id` filter.
- Rate limiting, structured error responses, request validation hardening.
- Production deployment of the backend (see [DEPLOYMENT.md](./DEPLOYMENT.md)) and Atlas index
  provisioning as a repeatable operational step rather than a manual one.

## Explicitly out of scope until a phase calls for it

Authentication, and the frontend streaming chat UI. (Automatic content extraction for Video and
URL resources — YouTube transcript fetch, and generic HTML/PDF fetch+extraction for other URLs —
is implemented, see Phase 3 above. Resource CRUD is Phase 2, document processing/chunking is
Phase 3,
Gemini embeddings + semantic vector search are Phase 4, hybrid retrieval + the RAG answer
pipeline — backend only — are Phase 5, concept/relationship extraction + graph
construction/centrality/traversal + `GET /api/v1/graph` are Phase 6, and the recommendations
heuristic + `GET /api/v1/recommendations` + the Recommendations page are Phase 7, all six
implemented. It's only the frontend chat UI that remains deferred, plus Phase 8's auth/hardening.)
