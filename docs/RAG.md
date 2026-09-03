# RAG pipeline

> Design document for retrieval and generation. **All six pipeline stages are now implemented**
> — chunking (Phase 3), embedding + semantic vector search (Phase 4), and hybrid retrieval +
> citations + generation (Phase 5): `retrieval.py`, `citations.py`, `pipeline.py`, and the new
> `generation.py` no longer raise `NotImplementedError`. See
> [DATABASE.md](./DATABASE.md#document_chunks), `backend/app/services/processing_service.py`,
> `backend/app/services/embedding_service.py`/`search_service.py`, and
> `backend/app/services/rag/*.py`. Only the frontend `ChatPanel`/Vercel AI SDK wiring is still
> deferred — see [ROADMAP.md](./ROADMAP.md).
>
> **Embedding provider: Gemini, not OpenAI.** The original scaffold assumed OpenAI
> `text-embedding-3-small`; this project deliberately uses Google's Gemini embedding API
> instead (`gemini-embedding-001` via the `google-genai` SDK) to use Gemini's free tier and
> minimize API cost. **Generation also uses Gemini** (`gemini-3.6-flash` by default,
> `GEMINI_CHAT_MODEL`) — the same SDK client, same API key, no second provider account. Nothing
> in this codebase calls the OpenAI API. See "Embedding provider abstraction" and "Generation
> provider abstraction" below.

StudyGraph answers questions over a user's own saved material using retrieval-augmented
generation with citations back to the source resource. All of this logic lives in the Python
backend; the frontend only ever sends a query and renders a streamed answer.

## Pipeline stages

1. **Ingest** — a resource is saved (`resources`, `status=pending`). Its content comes from
   whatever the user typed/pasted into `resource.content` (Phase 2) for Note/Article resources.
   Video and URL resources instead have their text fetched automatically during processing:
   a YouTube `source_url` (Video, or URL resources whose link is a YouTube video) has its
   transcript fetched via `app/services/ingestion/youtube_transcript.py`; any other URL is
   fetched and its readable text extracted via `app/services/ingestion/url_extraction.py`
   (HTML pages via `trafilatura`, direct PDF links via `pypdf`). Either fetch falls back to
   manually-provided `content` if it fails, and otherwise surfaces the fetch failure's own clear
   `processing_error` (Phase 3 note below).
2. **Chunk — implemented (Phase 3).** `POST /api/v1/resources/{id}/process`
   (`app/services/processing_service.py`) resolves the resource's text
   (`app/services/ingestion/content_extraction.py`), normalizes whitespace
   (`app/services/ingestion/normalization.py`), then splits it into token-bounded windows with
   `tiktoken` (`app/services/ingestion/chunking.py`): **512 tokens per chunk, 64-token overlap**
   by default, both configurable (`app/config.py`), never hard-coded. Each chunk becomes a
   `document_chunks` row via `app/db/chunk_repository.py`, which replaces a resource's prior
   chunks on every (re-)run rather than accumulating duplicates. The resource's `status` flips
   `pending → processing → ready` (or `failed`, with a `processing_error`) — see
   [DATABASE.md](./DATABASE.md#resources). **This stage does not embed anything** — chunks are
   plain text with `embedding=null`, ready for Phase 4 to fill in.

   Unlike the "paragraph/sentence boundary" splitting this document originally sketched, the
   implemented chunker uses a fixed token window over the whole normalized text — simpler,
   fully deterministic, and easier to reason about/test (see
   `backend/tests/test_chunking.py`); boundary-aware splitting can be revisited later if chunk
   quality turns out to need it.
3. **Embed — implemented (Phase 4).** `POST /api/v1/resources/{id}/embed`
   (`app/services/embedding_service.py`) embeds every not-yet-embedded chunk's `text` with
   **Gemini** `gemini-embedding-001` (via the `EmbeddingProvider` abstraction — see below) and
   stores the vector on that chunk's `embedding` field. Runs in batches
   (`EMBEDDING_BATCH_SIZE`, default 32 chunks per Gemini call), retries rate-limit/transient
   failures with exponential backoff, and is idempotent — already-embedded chunks are skipped,
   so re-running it after a partial failure only embeds what's still missing. The resource's
   `status` moves `ready → embedding → embedded` (or `failed`, with `processing_error`) — see
   [DATABASE.md](./DATABASE.md#resources).
4. **Retrieve — hybrid (vector + BM25) fusion implemented (Phase 5).**
   `app/services/rag/retrieval.py:hybrid_search`/`hybrid_search_with_scores` embeds the query
   with the same `EmbeddingProvider` (Gemini's `RETRIEVAL_QUERY` task type) and runs a MongoDB
   **Atlas Vector Search** (`$vectorSearch`, `app/db/chunk_repository.py:vector_search`,
   Phase 4) *concurrently* with an **Atlas Search** (`$search`, BM25-style full text,
   `chunk_repository.py:text_search`, Phase 5) query against `document_chunks`, both optionally
   pre-filtered by resource type/tags (resolved to a shared `resource_id` allowlist — see
   [DATABASE.md](./DATABASE.md#atlas-vector-search-setup)). The two ranked candidate lists are
   merged with **reciprocal rank fusion** (`RAG_RRF_K`, default `60`) rather than raw score
   normalization, since BM25's `searchScore` and cosine similarity live on incompatible scales
   — see "Why hybrid retrieval" below. If one retriever fails (e.g. its index isn't provisioned
   yet), retrieval degrades gracefully to the other side rather than failing outright; only both
   failing raises `RetrievalUnavailableError`. `POST /api/v1/search/vector`
   (`app/services/search_service.py`, Phase 4) still exists unchanged as the vector-only search
   preview endpoint — it does not use hybrid retrieval.
5. **Cite — implemented (Phase 5).** `app/services/rag/citations.py:build_citations` maps each
   retrieved chunk back to its resource (`resource_id`, title, type, a truncated snippet —
   `RAG_MAX_SNIPPET_CHARS`, default 320 chars, word-boundary-safe), producing the `Citation` list
   defined in `app/models/chat.py`, in the same order as the fused retrieval ranking. This is the
   full trail from an answer back to the exact source text; `app/services/rag/pipeline.py`
   attaches each citation's fused RRF score afterward (citations.py itself has no fusion
   context). Citation order **is** the numbering (`[1]`, `[2]`, ...) used in the LLM prompt.
6. **Generate — implemented (Phase 5).** `app/services/rag/pipeline.py` assembles retrieved
   chunks + citations + the user query into a numbered-excerpt prompt and streams it to
   **Gemini** (`gemini-3.6-flash` by default, `GEMINI_CHAT_MODEL`) via the `GenerationProvider`
   abstraction (see below). `POST /api/v1/chat` streams the answer as **Server-Sent Events** —
   a `citations` event first (even when empty), then `token` events, then a terminal `done` or
   `error` event — see [API.md](./API.md#apiv1chat-phase-5) for the exact event schema. The
   frontend's `ChatPanel` consuming these via the **Vercel AI SDK**, with `CitationBadge`
   components, is a separate, not-yet-implemented frontend pass (see
   [ROADMAP.md](./ROADMAP.md)) — the backend API is ready for it.

## Embedding provider abstraction

```
EmbeddingProvider (ABC)            app/services/rag/embeddings.py
    |
    `-- GeminiEmbeddingProvider    the only implementation; wraps google.genai
```

`embedding_service.py` and `search_service.py` depend on `EmbeddingProvider` and
`get_embedding_provider()` — never on `GeminiEmbeddingProvider` or `google.genai` directly, so
switching providers later (a local model, a different hosted API) is a change to
`get_embedding_provider()`'s dispatch plus a new class, not a rewrite of the pipeline.
`get_embedding_provider()` reads `settings.embedding_provider` (env var `EMBEDDING_PROVIDER`,
default and only supported value today: `gemini`) to decide which implementation to construct.

`GeminiEmbeddingProvider` calls `google.genai.Client(api_key=...).aio.models.embed_content(...)`
(the current, non-deprecated Google GenAI Python SDK — not the older `google-generativeai`
package) with `model="gemini-embedding-001"` (`GEMINI_EMBEDDING_MODEL`) and an
`EmbedContentConfig(task_type=..., output_dimensionality=...)`. `output_dimensionality`
(`GEMINI_EMBEDDING_DIMENSIONS`) is optional — Gemini's Matryoshka Representation Learning (MRL)
lets the model produce a smaller vector (768/1536/3072) on request; left unset, the model's own
default (3072) is used. Either way, the *actual* returned vector's length
(`len(embedding.values)`) is what gets stored and what the Atlas Vector Search index's
`numDimensions` must match — never a hard-coded assumption. See
[DATABASE.md](./DATABASE.md#atlas-vector-search-setup).

Errors are mapped to typed exceptions so callers can decide what's retryable:
`EmbeddingRateLimitError` (Gemini `429`), `EmbeddingTransientError` (Gemini `5xx`), and
`EmbeddingProviderError` (everything else — bad request, auth failure, misconfiguration, or an
unexpected response shape). `embedding_service.py` retries the first two with exponential
backoff (3 attempts) before giving up.

## Generation provider abstraction

```
GenerationProvider (ABC)           app/services/rag/generation.py
    |
    `-- GeminiGenerationProvider   the only implementation; wraps google.genai
```

Mirrors the embedding provider abstraction exactly. `app/services/rag/pipeline.py` depends on
`GenerationProvider` and `get_generation_provider()` — never on `GeminiGenerationProvider` or
`google.genai` directly. `get_generation_provider()` reads `settings.generation_provider` (env
var `GENERATION_PROVIDER`, default and only supported value today: `gemini`).

`GeminiGenerationProvider` calls
`google.genai.Client(api_key=...).aio.models.generate_content_stream(...)` — the **same SDK
client class** as `GeminiEmbeddingProvider`, and the **same `GEMINI_API_KEY`** — with
`model="gemini-3.6-flash"` (`GEMINI_CHAT_MODEL`) and a `GenerateContentConfig(system_instruction=...,
temperature=..., max_output_tokens=...)` (`GEMINI_CHAT_TEMPERATURE`/`GEMINI_CHAT_MAX_OUTPUT_TOKENS`).
Streams `GenerationChunk(text, finish_reason)` deltas as Gemini produces them; `finish_reason` is
set only on the terminal chunk of a successful stream.

Errors mirror the embedding provider's typed exceptions: `GenerationRateLimitError` (`429`),
`GenerationTransientError` (`5xx`), `GenerationProviderError` (everything else).
`app/services/rag/pipeline.py` retries only the **first** chunk of a stream on a rate-limit/
transient failure (3 attempts, exponential backoff — same budget as `embedding_service.py`); once
a chunk has reached the client, no further retry happens for that request — a later failure
becomes a terminal SSE `error` event instead (see "Generate" above and
[API.md](./API.md#apiv1chat-phase-5)).

## Why hybrid retrieval

Vector search alone misses exact-term matches (names, APIs, acronyms) that BM25-style search
catches; text search alone misses paraphrased or conceptually-related passages that don't
share vocabulary. Running both against Atlas's native indexes avoids standing up a separate
search engine (e.g. Elasticsearch) or a separate BM25 library — MongoDB Atlas Search already
implements it. The two ranked lists are merged with **reciprocal rank fusion** (RRF) rather than
normalizing and summing raw scores, since BM25's `searchScore` (unbounded, corpus-dependent) and
cosine similarity (`[0, 1]`) have no common scale — RRF only needs each list's rank order, not
its score distribution. Phase 4 shipped the vector half alone first (real, not a placeholder,
useful for the semantic search preview); Phase 5 adds the BM25 half and the fusion step, timed
alongside RAG chat where retrieval quality first actually matters for an answer.

## Module map

| Concern | Module | Status |
|---|---|---|
| Content extraction (per resource type) | `app/services/ingestion/content_extraction.py` | **implemented** (Phase 3) |
| Text normalization | `app/services/ingestion/normalization.py` | **implemented** (Phase 3) |
| Token-bounded chunking | `app/services/ingestion/chunking.py` | **implemented** (Phase 3) |
| Processing (chunking) orchestration | `app/services/processing_service.py` | **implemented** (Phase 3) |
| `document_chunks` persistence + chunk CRUD | `app/db/chunk_repository.py` | **implemented** (Phase 3-5) |
| Embedding provider abstraction (Gemini) | `app/services/rag/embeddings.py` | **implemented** (Phase 4) |
| Embedding orchestration (batching, retry) | `app/services/embedding_service.py` | **implemented** (Phase 4) |
| Semantic vector search (preview endpoint) | `app/services/search_service.py` + `chunk_repository.vector_search` | **implemented** (Phase 4, requires Atlas) |
| HTTP entry point (embed/search) | `app/api/v1/resources.py` (`/embed`), `app/api/v1/search.py` (`/vector`) | **implemented** (Phase 4) |
| Hybrid retrieval + RRF fusion | `app/services/rag/retrieval.py` | **implemented** (Phase 5, vector half requires Atlas, BM25 half requires Atlas Search) |
| Citation assembly | `app/services/rag/citations.py` | **implemented** (Phase 5) |
| Generation provider abstraction (Gemini) | `app/services/rag/generation.py` | **implemented** (Phase 5) |
| End-to-end RAG orchestration (streaming) | `app/services/rag/pipeline.py` | **implemented** (Phase 5) |
| HTTP entry point (chat) | `app/api/v1/chat.py` | **implemented** (Phase 5) |
