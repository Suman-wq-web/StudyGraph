# Development

Conventions for working in this codebase day-to-day. For first-time install, see
[SETUP.md](./SETUP.md).

## Project layout rules

- **Frontend and backend stay independent.** The frontend never imports backend code and
  never talks to MongoDB/OpenAI directly; it only calls `/api/v1/*` through
  `frontend/src/lib/api/client.ts`. See [ARCHITECTURE.md](./ARCHITECTURE.md).
- **Backend layering is one-directional:** `api/` → `services/` → `db/`. A route should never
  import from `db/` directly, and a service should never build an HTTP response.
- **`app/db/mongodb.py` is the only file that imports `motor`.** If you find yourself needing
  a database handle elsewhere, import `get_database()` from there rather than creating a new
  client.
- **AI/RAG/graph logic lives only under `app/services/rag/`, `app/services/ingestion/`, and
  `app/services/graph/`.** Routes and other services call into these, not into OpenAI/NetworkX
  directly. Note that not everything under `ingestion/` is AI-driven: chunking, normalization,
  and content extraction (Phase 3) are deterministic text processing with no model calls —
  they live there because they're pipeline stages feeding the eventual RAG/graph work, not
  because they use AI.
- **Cross-cutting orchestration services sit directly under `app/services/`,** alongside
  `resource_service.py` — e.g. `processing_service.py` (Phase 3) coordinates
  `ingestion/content_extraction.py` → `ingestion/normalization.py` → `ingestion/chunking.py` →
  `db/chunk_repository.py`. A service like this owns the sequencing of a pipeline; it doesn't
  contain the pipeline logic itself.
- **Slow per-resource work (processing, and anything similar later) runs as a FastAPI
  `BackgroundTasks` job, not inline in the request handler.** The route does the fast,
  synchronous part (validate the resource exists, flip its status) and schedules the rest;
  the client polls a status endpoint rather than the request blocking. This is deliberately
  not a task queue (Celery/RQ/etc.) — `BackgroundTasks` is built into FastAPI, and the
  processing pipeline's per-resource cost (tokenize + a few Mongo writes) doesn't yet justify
  the extra infrastructure. Revisit if/when a pipeline stage becomes slow enough to need
  retries, concurrency limits, or multi-process workers.

## Adding a new backend endpoint

1. Add the Pydantic request/response models to the relevant file in `app/models/` (or a new
   one if it's a new resource).
2. Add the route function to the matching module in `app/api/v1/` — the router is already
   mounted in `app/api/router.py`, so nothing else needs wiring.
3. Put the actual logic in `app/services/`, not in the route function. The route should just
   validate input, call a service function, and return its result.
4. Add a test under `backend/tests/`.

## Adding a new frontend page/component

1. Route pages live in `frontend/src/app/<route>/page.tsx`. Keep them thin — compose
   components from `frontend/src/components/*` rather than writing markup inline.
2. Feature-specific components go in the matching `components/<feature>/` folder; reusable
   primitives go in `components/ui/`.
3. If the page needs backend data, add a typed client function to `lib/api/<resource>.ts`
   (which calls through `lib/api/client.ts`) and a matching type in `lib/types/`.
4. Every data-bearing view should account for loading (`Skeleton`), empty (`EmptyState`), and
   error (`ErrorState`) states, not just the populated case.

## Testing

- **Backend:** `cd backend && pytest`. `requirements-dev.txt` adds `pytest` + `httpx` (needed
  for FastAPI's `TestClient`) on top of the runtime dependencies in `requirements.txt`. Tests
  that go through the API run against a real local MongoDB (`backend/tests/conftest.py` points
  `MONGODB_DB_NAME` at a separate `studygraph_test` database and clears `resources` and
  `document_chunks` before/after every test, so they never touch your dev data). Pure-logic
  modules with no Mongo/FastAPI dependency — `chunking.py`, `normalization.py`,
  `content_extraction.py` — are unit tested directly with no database at all.
- **Frontend:** `cd frontend && npm run build` is the primary check right now (it runs
  TypeScript type-checking as part of the build). No component test runner is set up yet —
  add one when there's real interactive logic to test, rather than pre-installing a framework
  for tests that don't exist yet.

## Style

- No comments explaining *what* code does — names should already say that. Comments are only
  for non-obvious *why* (a constraint, a workaround, an invariant).
- Don't add abstractions, config options, or error handling for cases that can't happen yet.
  A stub should be a stub (`raise NotImplementedError` or an empty router), not a
  half-implementation.
- Keep dependencies minimal — only add a package when the architecture actually calls for it
  (see the stack list in [ARCHITECTURE.md](./ARCHITECTURE.md)).

## Dependency changes

`requirements.txt` / `requirements-dev.txt` (backend) and `package.json` (frontend) are the
source of truth. If you add a dependency, update the relevant doc file too if it changes an
architectural decision (e.g. adding a new external service) — see
[ARCHITECTURE.md](./ARCHITECTURE.md) and [ROADMAP.md](./ROADMAP.md).
