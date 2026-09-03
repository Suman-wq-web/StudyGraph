# Environment variables

Two separate example files, one per app — never one shared `.env` for both, since the
frontend's env vars are (by Next.js convention) bundled into the client and must never carry
a secret.

- `frontend/.env.local.example` → copy to `frontend/.env.local`
- `backend/.env.example` → copy to `backend/.env`

Both example files contain placeholders only. Neither real `.env` file is committed —
both are excluded in `.gitignore`.

## Frontend (`frontend/.env.local`)

| Variable | Required | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | yes | Base URL of the FastAPI backend. `NEXT_PUBLIC_` prefix means this is exposed to the browser — it must never hold a secret. Defaults to `http://localhost:8000` for local dev only; set to the deployed backend's URL in production. |

## Backend (`backend/.env`)

| Variable | Required | Purpose |
|---|---|---|
| `MONGODB_URI` | yes | MongoDB Atlas connection string, including credentials. **Secret.** A real Atlas cluster (not a local `mongod`) is required for Atlas Vector Search — see [DATABASE.md](./DATABASE.md#atlas-vector-search-setup). |
| `MONGODB_DB_NAME` | yes | Database name (defaults to `studygraph`). |
| `ALLOWED_ORIGINS` | yes | Comma-separated list of origins allowed to call this API (CORS). Set to the exact deployed frontend origin in production — never `*`. |
| `CHUNK_SIZE_TOKENS` | no | Document-processing (Phase 3). Max tokens per chunk. Defaults to `512`. |
| `CHUNK_OVERLAP_TOKENS` | no | Document-processing (Phase 3). Token overlap between consecutive chunks. Defaults to `64`. |
| `TIKTOKEN_ENCODING` | no | Document-processing (Phase 3). `tiktoken` encoding name used for chunking. Defaults to `cl100k_base`. |
| `URL_FETCH_TIMEOUT_SECONDS` | no | Generic URL extraction (Phase 3, `app/services/ingestion/url_extraction.py`). Per-request HTTP timeout when fetching a non-YouTube URL resource. Defaults to `15`. |
| `URL_FETCH_MAX_BYTES` | no | Generic URL extraction (Phase 3). Response body size cap while fetching a non-YouTube URL resource; larger responses fail with a clear `processing_error` instead of being read in full. Defaults to `10000000` (10 MB). |
| `EMBEDDING_PROVIDER` | no | Embeddings (Phase 4). Selects the `EmbeddingProvider` implementation (`app/services/rag/embeddings.py`). Defaults to, and currently only supports, `gemini`. |
| `GEMINI_API_KEY` | yes (once embeddings/search are used) | **Gemini** — not OpenAI — embedding API key. Server-side only. **Secret.** Never sent to the frontend. Get a free-tier key at https://aistudio.google.com/apikey. |
| `GEMINI_EMBEDDING_MODEL` | no | Gemini embedding model name. Defaults to `gemini-embedding-001`. |
| `GEMINI_EMBEDDING_DIMENSIONS` | no | Output vector length via Gemini's Matryoshka Representation Learning (MRL) truncation — `768`, `1536`, or `3072`. Left unset, the model's own default (`3072`) is used. Whatever this resolves to **must match** the Atlas Vector Search index's `numDimensions` — see [DATABASE.md](./DATABASE.md#atlas-vector-search-setup). |
| `EMBEDDING_BATCH_SIZE` | no | Embeddings (Phase 4). Chunks sent per Gemini `embed_content()` call. Defaults to `32`. |
| `GENERATION_PROVIDER` | no | Chat generation (Phase 5). Selects the `GenerationProvider` implementation (`app/services/rag/generation.py`). Defaults to, and currently only supports, `gemini`. |
| `GEMINI_CHAT_MODEL` | no | Gemini chat/generation model name. Defaults to `gemini-3.6-flash`. Reuses `GEMINI_API_KEY` above -- no separate key. |
| `GEMINI_CHAT_TEMPERATURE` | no | Sampling temperature for generation. Defaults to `0.2` (favors grounded, less creative answers). |
| `GEMINI_CHAT_MAX_OUTPUT_TOKENS` | no | Max tokens Gemini may generate per answer. Defaults to `1024`. |
| `RAG_DEFAULT_TOP_K` | no | Hybrid retrieval (Phase 5). Chunks retrieved per chat query when the request doesn't specify `topK`. Defaults to `8`. |
| `RAG_CANDIDATE_MULTIPLIER` | no | Hybrid retrieval (Phase 5). Each retriever (vector, BM25) is queried for `max(topK * this, RAG_MIN_CANDIDATE_POOL)` candidates before fusion. Defaults to `4`. |
| `RAG_MIN_CANDIDATE_POOL` | no | Hybrid retrieval (Phase 5). Floor on the per-retriever candidate pool size. Defaults to `20`. |
| `RAG_RRF_K` | no | Hybrid retrieval (Phase 5). Reciprocal rank fusion constant. Defaults to `60` (the standard literature value). |
| `RAG_MAX_SNIPPET_CHARS` | no | Hybrid retrieval (Phase 5). Citation snippet truncation length; the full chunk text still goes into the LLM prompt. Defaults to `320`. |
| `EXTRACTION_MAX_CONCEPTS_PER_CHUNK` | no | Knowledge graph extraction (Phase 6). Caps how many concepts the extraction prompt asks Gemini to identify per chunk. Defaults to `8`. No separate provider/model/key setting exists for this phase — it reuses `GEMINI_API_KEY`/`GEMINI_CHAT_MODEL` via the same, unmodified `GenerationProvider` Phase 5 chat uses (see [KNOWLEDGE_GRAPH.md](./KNOWLEDGE_GRAPH.md)). |

Loaded by `backend/app/config.py` via `pydantic-settings`, which reads `backend/.env`
locally and real environment variables in any deployed environment (Render/Fly/Railway/etc.
inject these through their own dashboard/CLI, not a checked-in file).

**Gemini, not OpenAI, is the embedding provider** — a deliberate change from the original
scaffold, to use Google's free tier and minimize API cost. Nothing in this codebase calls the
OpenAI API. See [RAG.md](./RAG.md) ("Embedding provider abstraction") and
[ARCHITECTURE.md](./ARCHITECTURE.md). **Gemini is also the chat/generation provider (Phase 5)**
— `GEMINI_CHAT_MODEL` reuses the same `GEMINI_API_KEY` and the same `google-genai` SDK client as
embeddings; see [RAG.md](./RAG.md) ("Generation provider abstraction").

## Rules

- Never commit a real `.env` or `.env.local` file — both are gitignored.
- Never put a secret behind a `NEXT_PUBLIC_` prefix.
- Local-dev-only defaults (like the `localhost` fallback in `app/config.py` and
  `frontend/src/lib/api/client.ts`) exist so the app runs out of the box in development; every
  deployed environment must set the real value explicitly rather than relying on the fallback.
