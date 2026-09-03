# Deployment

## Frontend → Vercel

`frontend/` is a standard Next.js 14 App Router project with no custom build steps, so it
deploys to Vercel with **zero extra configuration** — no `vercel.json` is checked in, and none
is required. To deploy:

1. Create a Vercel project pointing at this repository.
2. Set the project's **Root Directory** to `frontend/`.
3. Framework preset: Next.js (auto-detected).
4. Set the single environment variable the frontend reads: `NEXT_PUBLIC_API_BASE_URL`,
   pointing at the deployed backend's URL.

Nothing else is needed. If build customization is ever required (custom headers, redirects,
a monorepo build command override), add `frontend/vercel.json` at that point — it's
deliberately omitted now because there's nothing to configure yet, and an empty/boilerplate
`vercel.json` would only be a file to keep in sync for no benefit.

## Backend → a persistent host (not Vercel serverless)

The FastAPI backend is intentionally **not** targeted at Vercel's Python serverless
functions. Reasons:

- It holds a long-lived Motor (MongoDB) client rather than opening a connection per request.
- Knowledge-graph construction builds an in-memory NetworkX graph per request, which is
  computationally heavier than a typical serverless function is suited for.
- RAG queries chain multiple network calls (retrieval → generation, possibly streamed) that
  benefit from a warm, long-running process rather than cold starts.

Recommended targets: **Render, Fly.io, Railway, or a Docker container on any VM.** All of them
support:

- A standard `uvicorn main:app` (or `uvicorn main:app --host 0.0.0.0 --port $PORT`) start
  command.
- Environment variables set through their dashboard/CLI (see
  [ENVIRONMENT.md](./ENVIRONMENT.md)).
- Outbound HTTPS to MongoDB Atlas and the **Gemini API** (embeddings, Phase 4 — not OpenAI;
  see [RAG.md](./RAG.md)).

Vercel Python functions remain an option later for a single, genuinely lightweight endpoint,
but they are not the default deployment target for this service.

## Database → MongoDB Atlas

Fully managed. **Atlas Vector Search is implemented (Phase 4)** and requires a real Atlas
cluster — a local `mongod` cannot run `$vectorSearch` at all — see
[DATABASE.md](./DATABASE.md#atlas-vector-search-setup) for the index definition and setup
steps. **Atlas Search (BM25 full-text)** for hybrid retrieval is still planned (Phase 5, not
yet implemented) — see [RAG.md](./RAG.md). Either way, there's no separate search
infrastructure (e.g. Elasticsearch) to deploy or operate; both live on the same Atlas cluster.

## Topology

```
Browser ──HTTPS──▶ Vercel (frontend)
                        │
                        ▼ HTTPS (NEXT_PUBLIC_API_BASE_URL)
                  Persistent host (backend, FastAPI)
                        │
            ┌───────────┼───────────┐
            ▼                       ▼
     MongoDB Atlas             Gemini API
  (+ Atlas Vector Search)   (embeddings, Phase 4)
```

The frontend has no network path to MongoDB or Gemini — it only ever calls the backend.
**Gemini, not OpenAI, is the embedding provider** — see [RAG.md](./RAG.md) and
[ENVIRONMENT.md](./ENVIRONMENT.md).

## Readiness checklist for this phase

- [x] Frontend builds cleanly with no server-only secrets baked into client bundles (only
      `NEXT_PUBLIC_*` vars are read client-side).
- [x] Backend reads all configuration from environment variables (`app/config.py`); no secret
      is hardcoded.
- [x] No `.env` file is committed; `.env.example` files contain placeholders only.
- [x] Atlas Vector Search index (`document_chunks_vector_index`) documented, with exact setup
      steps — see [DATABASE.md](./DATABASE.md#atlas-vector-search-setup). Not yet
      auto-provisioned; provisioning it (and the standard, non-search indexes) as a repeatable
      operational step is deferred to Phase 8 (see [ROADMAP.md](./ROADMAP.md)).
- [ ] Atlas Search (BM25 text) index for hybrid retrieval — deferred to Phase 5 (see
      [ROADMAP.md](./ROADMAP.md)).
- [ ] Backend hosting account/service actually created — deferred until there's a real
      endpoint worth deploying.
