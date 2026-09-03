# Architecture

> Status: Phase 7 (recommendations). Resource CRUD (Phase 2), extract-normalize-chunk
> processing (Phase 3), Gemini embeddings + semantic vector search (Phase 4), hybrid (vector +
> BM25) retrieval with Gemini-generated, cited chat answers (Phase 5), concept/relationship
> extraction + NetworkX graph construction/analysis (Phase 6), and deterministic
> centrality/gap-based recommendations (Phase 7) are all implemented end-to-end; only the
> frontend `ChatPanel`/Vercel AI SDK wiring remains, plus Phase 8's auth/hardening. See
> [ROADMAP.md](./ROADMAP.md) for what's next.

## System overview

StudyGraph is two independently deployable applications that communicate over HTTP:

```
┌─────────────────────┐        HTTPS (REST + streaming)        ┌──────────────────────┐
│   frontend/          │ ─────────────────────────────────────▶ │   backend/             │
│   Next.js 14 (TS)     │                                        │   FastAPI (Python)      │
│   Deploys to Vercel    │ ◀───────────────────────────────────── │   Deploys to a persistent│
│                          │              JSON / SSE               │   host (see DEPLOYMENT.md)│
└─────────────────────┘                                        └──────────┬───────────┘
                                                                            │
                                                        ┌───────────────────┼───────────────────┐
                                                        ▼                   ▼                   ▼
                                                  MongoDB Atlas       Gemini API           NetworkX
                                             (data + Atlas Search +  (embeddings Phase 4, (in-memory
                                              Atlas Vector Search)   generation Phase 5)   graph, per request)
```

The frontend never talks to MongoDB or Gemini directly — every data or AI operation goes
through the FastAPI backend's versioned REST API. See [API.md](./API.md) for the contract.
**Gemini, not OpenAI, is the embedding provider** (a deliberate change from the original plan,
to use Google's free tier and minimize cost) — see [RAG.md](./RAG.md) for the embedding
provider abstraction this is built behind, and [ENVIRONMENT.md](./ENVIRONMENT.md) for the
`GEMINI_API_KEY`/`EMBEDDING_PROVIDER` variables. Nothing in this codebase calls the OpenAI API.

## Frontend architecture

```
frontend/
  src/
    app/                 # Next.js App Router — one route per top-level nav item
      dashboard/          library/  graph/  chat/  recommendations/  settings/
    components/
      layout/              Sidebar, Topbar, ThemeProvider/Toggle, SidebarContext
      dashboard/            Dashboard-specific widgets (StatCard)
      resources/             Resource library widgets (Card/List/FormDialog/DetailDialog)
      graph/                  Knowledge graph visualization wrapper -- KnowledgeGraphView
                                 renders real data via react-force-graph-2d (Phase 6)
      chat/                    AI Assistant (RAG chat) UI -- still a placeholder (Phase 5)
      search/                   SemanticSearchPanel: raw vector-search preview (Phase 4),
                                  rendered on the /chat page above the (still placeholder) ChatPanel
      recommendations/          Learning recommendation widgets -- RecommendationCard renders
                                  real data (Phase 7)
      ui/                        Design-system primitives: Button, Card, Badge, Input, Textarea,
                                   Select, Modal, ConfirmDialog, Toast, PageHeader, EmptyState,
                                   ErrorState, LoadingState, Skeleton, icons.tsx (hand-rolled
                                   outline icon set, no icon package dependency)
    lib/
      api/                 One client module per backend resource, all routed through client.ts
                             (resources.ts, search.ts, chat.ts, graph.ts, recommendations.ts)
      types/                TypeScript types mirroring backend Pydantic models
                             (resource.ts, search.ts, chat.ts, graph.ts, edge.ts, concept.ts,
                             recommendation.ts)
      hooks/                 Small reusable hooks (useToast — per-page toast queue)
      utils/                 Pure helpers (cn())
```

**Conventions:**
- Only `lib/api/client.ts` reads `NEXT_PUBLIC_API_BASE_URL`. Every other `lib/api/*` module
  calls through it, so the backend origin is swappable in one place. It also parses FastAPI's
  `422` validation body into per-field messages (`ApiError.fieldErrors`) so forms can highlight
  the specific input, not just show a generic error banner.
- Components are grouped by feature, with a shared `ui/` layer for primitives. Every form field
  (`Input`, `Textarea`, `Select`) and status indicator (`Badge`) is a shared primitive rather
  than ad hoc markup, so validation/focus/error styling stays consistent across the app.
- Theming is CSS-variable based (`app/globals.css` defines light/dark tokens, including a
  `danger` token so destructive/error UI never hardcodes a red shade; `ThemeProvider` toggles a
  `.dark` class on `<html>`). Tailwind colors (`base`, `content`, `accent`, `danger`) resolve to
  those variables — no component hardcodes a color. Body typeface is self-hosted Inter via
  `next/font/google` (no extra dependency, no runtime request to Google Fonts).
- `SidebarContext` (a small client-side provider mounted in the root layout) tracks whether
  the mobile nav drawer is open; `Sidebar` renders as a slide-over drawer below the `md`
  breakpoint and a fixed column above it, and `Topbar` exposes the hamburger button that
  toggles it. Every page is responsive by construction rather than by per-page effort.
- Every data-bearing view renders loading (`Skeleton` for lists, `LoadingState` for full-section
  spinners), empty (`EmptyState`), and error (`ErrorState`) states in addition to its populated
  state. `/graph` (Phase 6) and `/recommendations` (Phase 7) both load real data with this
  full state set; `/chat` still uses `EmptyState` plus a `Badge` naming the phase that will
  implement it, rather than fabricating data.

Full page-by-page description: none needed beyond the route list above — each page under
`app/*/page.tsx` is a thin composition of the components in `components/*`.

## Backend architecture

```
backend/
  main.py                # FastAPI app: CORS, lifespan (DB connect/close), /health, mounts api_router
  app/
    config.py              # pydantic-settings Settings, loaded from environment/.env
    api/
      router.py             # aggregates all v1 routers under /api/v1
      v1/                     # one module per concern: resources, search, chat, graph,
                                # recommendations (Phase 7)
    db/
      mongodb.py              # the ONLY module that imports motor
      collections.py           # collection name constants + planned index definitions
      resource_repository.py    # resources collection CRUD (docs <-> Resource* models)
      chunk_repository.py        # document_chunks CRUD, idempotent replace-on-(re)process,
                                   # + vector_search() -- the only function that runs $vectorSearch
                                   # + list_unextracted_by_resource()/set_concepts_extracted() (Phase 6)
      concept_repository.py       # concepts CRUD + upsert-by-normalized-name — implemented (Phase 6)
      edge_repository.py           # edges CRUD + upsert-by-(source,target,relation_type) — implemented (Phase 6)
    models/                     # Pydantic schemas, one file per MongoDB collection (+ chat DTOs)
      processing.py               # ProcessingStatusResponse (GET .../processing-status)
      embedding.py                 # EmbeddingStatusResponse, VectorSearchRequest/Response (Phase 4)
      chat.py                       # ChatQueryRequest/Response, Citation, SSE event DTOs (Phase 5)
      graph.py                      # GraphResponse, ExtractionTriggerResponse/StatusResponse (Phase 6)
      concept.py, edge.py            # Concept/ConceptEdge collection schemas — implemented (Phase 6)
      recommendation.py               # Recommendation, RecommendationResponse (Phase 7)
    services/
      resource_service.py       # business logic for saving/listing/updating/deleting resources
      processing_service.py      # orchestrates extract -> normalize -> chunk -> persist (Phase 3)
      embedding_service.py        # orchestrates chunk -> embed (batched, retried) -> store (Phase 4)
      search_service.py            # embeds a query, runs vector_search, joins resource metadata (Phase 4)
      graph_extraction_service.py   # orchestrates chunk -> extract -> resolve/dedupe -> upsert
                                      # concepts/edges (Phase 6)
      graph_service.py               # orchestrates builder.py + traversal.py for GET /api/v1/graph,
                                       # writes centrality back to concepts (Phase 6)
      recommendation_service.py       # orchestrates builder.py + traversal.py + graph/recommendations.py
                                        # for GET /api/v1/recommendations (Phase 7); does NOT write
                                        # centrality back -- that stays graph_service.py's job
      ingestion/
        content_extraction.py      # per-resource-type text resolution — implemented (Phase 3)
        youtube_transcript.py       # YouTube transcript fetch (Video, and URL resources whose
                                      # link is YouTube) — implemented (Phase 3)
        url_extraction.py            # generic (non-YouTube) URL fetch + readable-text extraction:
                                       # HTML via trafilatura, direct PDF via pypdf, plus an SSRF
                                       # guard — implemented (Phase 3)
        normalization.py            # whitespace cleanup before chunking — implemented (Phase 3)
        chunking.py                  # tiktoken 512-token/64-overlap chunker — implemented (Phase 3)
        extraction.py                 # concept/relation extraction — implemented (Phase 6); calls
                                        # rag/generation.py's existing GenerationProvider unmodified
      rag/
        embeddings.py                 # EmbeddingProvider abstraction + GeminiEmbeddingProvider —
                                        # implemented (Phase 4)
        generation.py                  # GenerationProvider abstraction + GeminiGenerationProvider —
                                         # implemented (Phase 5), left untouched by Phase 6.
                                         # embeddings.py and generation.py are the only two modules
                                         # that import google.genai
        retrieval.py                    # hybrid_search/hybrid_search_with_scores: vector + BM25 +
                                          # reciprocal rank fusion — implemented (Phase 5)
        citations.py                     # build_citations: chunk -> resource join + snippet —
                                           # implemented (Phase 5)
        pipeline.py                       # retrieve_context/stream_generation/answer_query: end-to-end
                                            # RAG orchestration, SSE event generation — implemented
                                            # (Phase 5), left untouched by Phase 6
      graph/                       # NetworkX graph builder + centrality/traversal — implemented (Phase 6)
        builder.py                    # build_user_graph: concepts+edges -> nx.DiGraph
        traversal.py                   # compute_centrality (betweenness), suggest_learning_path
                                         # (prerequisite_of topological sort)
        recommendations.py              # find_gaps/find_next_steps: pure, deterministic v1
                                          # heuristics over the graph — implemented (Phase 7)
    core/
      logging.py                   # basic logging setup
  tests/
    conftest.py                     # TestClient fixture; points MONGODB_DB_NAME at studygraph_test;
                                      # cleans resources/document_chunks/concepts/edges per test
    test_health.py                 # GET /health -> 200
    test_resources.py               # create/list/get/update/delete + validation errors
    test_chunking.py                # chunking algorithm — no DB, no FastAPI
    test_normalization.py            # whitespace cleanup — no DB, no FastAPI
    test_content_extraction.py        # per-resource-type extraction — no DB, no FastAPI
    test_url_extraction.py             # generic URL fetch/extract: SSRF guard, content-type
                                         # detection, HTML/PDF extraction — mocked httpx transport,
                                         # no DB, no real network
    test_processing.py                 # POST .../process + GET .../processing-status, idempotency
    test_embeddings.py                  # EmbeddingProvider/GeminiEmbeddingProvider — mocked SDK client
    test_embedding_pipeline.py           # POST .../embed + .../embedding-status, retry, idempotency
    test_search.py                        # POST /search/vector — mocked provider + vector_search
    test_gemini_integration.py             # opt-in, real Gemini embedding call — skipped unless enabled
    test_atlas_integration.py               # opt-in, real Atlas vector search — skipped unless enabled
    test_chunk_repository.py                 # get_many_by_ids — real local Mongo, no Atlas needed
    test_generation.py                        # GenerationProvider/GeminiGenerationProvider — mocked SDK
    test_retrieval.py                          # hybrid_search fusion/filtering/partial-failure — mocked
    test_citations.py                           # build_citations — real local Mongo, no Atlas needed
    test_chat_pipeline.py                        # retrieve_context/stream_generation/answer_query — mocked
    test_chat_api.py                              # POST /api/v1/chat — mocked, SSE streaming assertions
    test_gemini_chat_integration.py                # opt-in, real Gemini generation call — skipped unless enabled
    test_rag_chat_integration.py                    # opt-in, real end-to-end RAG chat — skipped unless enabled
    test_graph_extraction.py                         # extract_from_chunk JSON parsing/retry — mocked provider
    test_concept_repository.py                        # concept upsert/dedupe — real local Mongo
    test_edge_repository.py                            # edge upsert/evidence — real local Mongo
    test_graph_builder.py                               # build_user_graph — no DB, monkeypatched repos
    test_graph_traversal.py                              # centrality/learning-path — no DB, no FastAPI
    test_graph_extraction_pipeline.py                     # POST .../extract + .../extraction-status,
                                                            # dedupe/idempotency/partial-failure — mocked
    test_graph_api.py                                      # GET /api/v1/graph — real local Mongo
    test_recommendation_algorithm.py                        # find_gaps/find_next_steps — no DB, no FastAPI
    test_recommendations_api.py                              # GET /api/v1/recommendations — real local Mongo
```

**Conventions:**
- **Isolation of DB access:** `app/db/mongodb.py` is the only module that imports `motor`.
  Services receive a database handle from `get_database()`; they never construct their own
  client.
- **Isolation of AI/RAG logic:** everything under `app/services/rag/` and
  `app/services/ingestion/` is the only code that will ever call an AI provider. Routes in
  `app/api/v1/*` stay thin — they validate input/output shape and delegate to `app/services/*`.
- **Provider abstraction, not a direct SDK dependency:** `app/services/rag/embeddings.py`
  defines an `EmbeddingProvider` ABC; `GeminiEmbeddingProvider` is the only implementation, and
  `get_embedding_provider()` (driven by `settings.embedding_provider`) is the only thing the
  rest of the app calls. `app/services/rag/generation.py` mirrors this exactly for chat
  generation: `GenerationProvider` ABC, `GeminiGenerationProvider`, `get_generation_provider()`
  (driven by `settings.generation_provider`). `embedding_service.py`, `search_service.py`, and
  `app/services/rag/pipeline.py` depend on these abstractions — none imports `google.genai`
  directly, so swapping providers later is a config change, not a rewrite. `embeddings.py` and
  `generation.py` are the *only two* modules that import `google.genai`, mirroring how
  `app/db/mongodb.py` is the only module that imports `motor`.
- **Layering:** `api/` (HTTP) → `services/` (business logic) → `db/` (persistence). Routes
  never call `db/` directly; services never build HTTP responses. `embedding_service.py`,
  `search_service.py`, `graph_extraction_service.py`, and `graph_service.py` sit alongside
  `resource_service.py`/`processing_service.py` at the `services/` level (cross-cutting
  orchestration) rather than inside `ingestion/` or `graph/`, which hold the individual
  pipeline stages those orchestrators call.
- **Config:** all secrets and external endpoints come from environment variables via
  `app/config.py`. Nothing is hardcoded — including the embedding vector's dimension, which is
  read off the actual Gemini response rather than assumed (see [DATABASE.md](./DATABASE.md)).
  See [ENVIRONMENT.md](./ENVIRONMENT.md).

`app/services/rag/embeddings.py` (Phase 4), `retrieval.py`/`citations.py`/`generation.py`/
`pipeline.py` (Phase 5), `app/services/ingestion/extraction.py`/`app/services/graph/`/
`graph_extraction_service.py`/`graph_service.py` (Phase 6), and
`app/services/graph/recommendations.py`/`recommendation_service.py` (Phase 7) are all
implemented — the Phase 6 group deliberately calls `rag/generation.py`'s existing
`GenerationProvider` interface without modifying that file, and the Phase 7 heuristics call no
provider at all (see [KNOWLEDGE_GRAPH.md](./KNOWLEDGE_GRAPH.md)). Every backend module listed
above is now implemented; only the frontend `ChatPanel`/Vercel AI SDK wiring and Phase 8's
auth/hardening remain — see [ROADMAP.md](./ROADMAP.md).

## API boundaries

- All backend routes are versioned under `/api/v1`: `/resources`, `/search`, `/chat`, `/graph`,
  `/recommendations`. Full contract in [API.md](./API.md).
- The frontend has no MongoDB driver, no Gemini SDK, and no server-side secret — it only
  calls the backend.
- `/health` is unauthenticated and outside `/api/v1` — a plain liveness check for the
  deployment platform.

## Related documents

- [SETUP.md](./SETUP.md) — first-time install and run instructions
- [DEVELOPMENT.md](./DEVELOPMENT.md) — day-to-day conventions, testing, adding new modules
- [API.md](./API.md) — endpoint contract and conventions
- [DATABASE.md](./DATABASE.md) — MongoDB collections, fields, indexes
- [RAG.md](./RAG.md) — retrieval-augmented generation pipeline design
- [KNOWLEDGE_GRAPH.md](./KNOWLEDGE_GRAPH.md) — concept/relationship graph pipeline design
- [DEPLOYMENT.md](./DEPLOYMENT.md) — where and how each app deploys
- [ENVIRONMENT.md](./ENVIRONMENT.md) — every environment variable, what reads it, why
- [ROADMAP.md](./ROADMAP.md) — phased plan from this scaffold to a working product
