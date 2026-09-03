# Database

StudyGraph uses **MongoDB Atlas** as its only datastore, including Atlas's built-in **Atlas
Search** (full-text/BM25-style) and **Atlas Vector Search** indexes — no separate search
infrastructure to run. All access goes through `backend/app/db/mongodb.py` and the Pydantic
schemas in `backend/app/models/`; collection names and index plans are centralized in
`backend/app/db/collections.py`.

`document_chunks` is designed to be scoped by `user_id` once auth lands (Phase 8) — see below
for current status. `concepts` and `edges` already carry a `user_id` field (Phase 6), but there
is no auth system yet, so every row currently gets the same placeholder value.

## `resources`

One saved article, video, URL, or note. **Implemented in Phase 2** — see
`backend/app/api/v1/resources.py`, `backend/app/services/resource_service.py`, and
`backend/app/db/resource_repository.py` for the full read/write path.

| field | type | notes |
|---|---|---|
| `_id` | ObjectId | exposed to clients as `id` (string) |
| `type` | enum | `article` \| `video` \| `url` \| `note` |
| `title` | string | 1-200 chars, trimmed, required |
| `description` | string? | optional short summary, max 2000 chars |
| `source_url` | string? | must start with `http://`/`https://` when present; null for raw notes |
| `content` | string? | raw/extracted text, max 200,000 chars |
| `tags` | string[] | lowercased, deduplicated, max 20 tags of 50 chars each |
| `status` | enum | `pending` \| `processing` \| `ready` \| `embedding` \| `embedded` \| `failed` — spans both the chunking (Phase 3, `app/services/processing_service.py`) and embedding (Phase 4, `app/services/embedding_service.py`) pipelines. Every resource starts `pending`; `POST /{id}/process` drives it to `ready` (chunked); `POST /{id}/embed` (only valid from `ready`/`embedded`/`failed`, and only once chunks exist) drives it to `embedded`. Re-chunking (re-running `/process`) replaces all chunks and their embeddings, dropping status back to `ready` -- it must be re-embedded. |
| `processing_error` | string? | max 2000 chars; set when `status=failed` with a short, user-safe reason (never a stack trace); cleared on the next successful process |
| `created_at`, `updated_at` | datetime | server-assigned, UTC |

`user_id` is intentionally **not** on this collection yet — it's added in Phase 8 once real
auth exists, at which point every repository query gets a `user_id` filter. `processing_error`
is server-managed: it's on the `Resource` response model but deliberately absent from
`ResourceCreate`/`ResourceUpdate`, so a client can't fabricate it via `PATCH` — only
`app/db/resource_repository.py:set_processing_state` writes it.

Model: `backend/app/models/resource.py`. Index `(type, created_at desc)` is planned (see
`app/db/collections.py`) but not yet provisioned — Phase 2 runs fine without it at
development-data volumes; provisioning real indexes is deferred to the same operational pass
described in [ROADMAP.md](./ROADMAP.md) Phase 8.

## `document_chunks`

The retrieval unit for future RAG — a resource's text split into token-bounded pieces, now with
an optional embedding vector. Chunking is **implemented in Phase 3**
(`app/services/processing_service.py`); embedding is **implemented in Phase 4**
(`app/services/embedding_service.py`). `embedding` is `null` until a chunk is successfully
embedded — **failed chunks never get a partial/fake vector written**.

| field | type | notes |
|---|---|---|
| `_id` | ObjectId | exposed to clients as `id` (string) |
| `resource_id` | string | FK to `resources._id` (plain string, not a native ObjectId reference); also the field the Atlas Vector Search index filters on -- see below |
| `chunk_index` | int | 0-based order within the resource |
| `text` | string | decoded straight from its token window — never re-stripped, so `token_count` always matches. Embedding a chunk never modifies `text`, `token_count`, or `chunk_index` -- only `embedding` and `updated_at` change. |
| `token_count` | int | via `tiktoken` (`cl100k_base` by default), equals `end_token - start_token` |
| `start_token`, `end_token` | int | the chunk's token-index window in the resource's normalized text (`end_token` exclusive); consecutive chunks overlap by `chunk_overlap_tokens` |
| `embedding` | float[]? | **Gemini** `gemini-embedding-001` vector (NOT OpenAI) via the `EmbeddingProvider` abstraction (`app/services/rag/embeddings.py`); `null` until embedded. Length is whatever `GEMINI_EMBEDDING_DIMENSIONS` resolves to (3072 by default) -- never hard-coded, always read off the actual API response. |
| `concepts_extracted` | bool | **Phase 6.** `false` until a concept/relationship extraction pass has been attempted for this chunk (whether or not it yielded any concepts) -- see `app/services/graph_extraction_service.py`. Mirrors `embedding`'s null-until-done idempotency signal; missing on documents written before Phase 6 (treated as `false`). |
| `metadata` | object | `heading`, `page_number`, `start_time_seconds`/`end_time_seconds` (video) — reserved for future citation context, not populated yet |
| `created_at`, `updated_at` | datetime | server-assigned, UTC |

Model: `backend/app/models/chunk.py`. Not scoped by `user_id` yet, matching `resources` (see
above). **Chunking algorithm:** fixed token window over the whole normalized text — 512 tokens
per chunk with a 64-token overlap by default (`app/config.py`:
`chunk_size_tokens`/`chunk_overlap_tokens`, overridable per call, never hard-coded elsewhere).
The last chunk always reaches the end of the token stream, so content is never silently
truncated; a token window that would decode to only whitespace is skipped rather than stored as
an empty chunk. Pure and deterministic — see `app/services/ingestion/chunking.py` and its unit
tests (`backend/tests/test_chunking.py`) for the exact guarantees.

**Idempotent (re-)processing:** `chunk_repository.replace_chunks_for_resource` deletes a
resource's existing chunks before inserting the newly produced set, so re-processing (e.g.
after editing a resource's content) replaces rather than accumulates -- and drops any
embeddings those old chunks had, since the new chunk documents start with `embedding=null`.
Deleting a resource (`DELETE /api/v1/resources/{id}`) cascades to delete its chunks too.

**Idempotent (re-)embedding:** `embedding_service.run_embedding` only ever queries chunks where
`embedding` is still `null` (`chunk_repository.list_unembedded_by_resource`) and writes one
chunk's vector at a time, only once the full vector for that chunk is in hand -- so re-running
`POST /{id}/embed` never re-calls Gemini for a chunk that's already embedded, and a
failure partway through a resource's chunks leaves the ones that succeeded embedded (with real
vectors) and the rest `null`, never a truncated/partial vector for any single chunk. See
[API.md](./API.md#apiv1resourcesidembed-phase-4) for the retry/error behavior at the request
level.

Standard index (planned, not yet provisioned — see `app/db/collections.py`, same
deferred-until-Phase-8 status as `resources`): `(resource_id, chunk_index)`.

### Atlas Vector Search setup

Semantic retrieval (`app/db/chunk_repository.py:vector_search`, used by
`POST /api/v1/search/vector`) runs MongoDB's native `$vectorSearch` aggregation stage. **This
requires a real MongoDB Atlas cluster** — a local `mongod` (the default for everything else in
this project) does not support `$vectorSearch` at all; running it against one raises an
`OperationFailure`, which `search_service.py` catches and reports as a clear
`503 Service Unavailable` rather than crashing or silently returning nothing. There is
deliberately no Python-side cosine-similarity fallback: production always uses real Atlas
Vector Search, so nothing in this codebase pretends otherwise, even for local development.

| | |
|---|---|
| **Index name** | `document_chunks_vector_index` (`ATLAS_VECTOR_INDEX_NAME` in `app/db/collections.py`) |
| **Collection** | `document_chunks` |
| **Vector field** | `embedding` (`ATLAS_VECTOR_INDEX_FIELD`) |
| **Dimensions** | Must match whatever `GEMINI_EMBEDDING_DIMENSIONS` resolves to -- **3072** if unset (gemini-embedding-001's own default; `GEMINI_EMBEDDING_MODEL_DEFAULT_DIMENSIONS` in `app/db/collections.py`), or 768/1536/3072 if you set it explicitly for a smaller (Matryoshka-truncated) vector. Whatever you choose, the index's `numDimensions` **must equal `len(embedding)`** on the stored chunks, or Atlas rejects/mismatches queries. |
| **Similarity metric** | `cosine` (`ATLAS_VECTOR_INDEX_SIMILARITY`) |
| **Filter fields** | `resource_id` (`ATLAS_VECTOR_INDEX_FILTER_FIELDS`) — lets `vector_search()` pre-filter to a specific set of resources (used for the `resourceType`/`tags` filters on `POST /search/vector`; resolved to a `resource_id` allowlist by `search_service.py` rather than denormalizing resource metadata onto every chunk) |

**Atlas UI / `mongosh` index definition** (Atlas Search → Create Search Index → JSON Editor,
or `db.document_chunks.createSearchIndex(...)` with `type: "vectorSearch"`):

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 3072,
      "similarity": "cosine"
    },
    {
      "type": "filter",
      "path": "resource_id"
    }
  ]
}
```

**Setup steps:**
1. Create (or use an existing) MongoDB Atlas cluster — the free M0 tier supports Atlas Vector
   Search.
2. Set `MONGODB_URI` in `backend/.env` to that cluster's connection string (see
   [ENVIRONMENT.md](./ENVIRONMENT.md)); local development against a plain `mongod` still works
   for everything except vector search itself.
3. Save at least one resource, `POST /{id}/process` (chunk it), then `POST /{id}/embed` (embed
   it with Gemini) so `document_chunks.embedding` actually has vectors of a known length.
4. In the Atlas UI, open the target database → **Search** tab → **Create Search Index** → JSON
   Editor → paste the definition above (adjusting `numDimensions` to match step 3's actual
   vector length) → index it on the `document_chunks` collection → name it
   `document_chunks_vector_index`.
5. Wait for the index to finish building (Atlas shows its status), then `POST /search/vector`
   should return real results.

### Atlas Search (BM25) setup

The keyword half of hybrid retrieval (`app/db/chunk_repository.py:text_search`, used by
`app/services/rag/retrieval.py:hybrid_search` for `POST /api/v1/chat`) runs MongoDB's native
`$search` aggregation stage (the `text` operator). Like `$vectorSearch`, this **requires a real
MongoDB Atlas cluster** — a local `mongod` raises an `OperationFailure` for the unrecognized
stage. Unlike `/search/vector`, a missing/unsupported index here does **not** fail the whole
request: `app/services/rag/retrieval.py` catches this per-retriever and degrades gracefully to
vector-only results (see [RAG.md](./RAG.md#why-hybrid-retrieval)); only a `$vectorSearch`
**and** `$search` failing together raises `RetrievalUnavailableError`.

| | |
|---|---|
| **Index name** | `document_chunks_text_search` (`ATLAS_SEARCH_INDEX_NAME` in `app/db/collections.py`) |
| **Collection** | `document_chunks` |
| **Type** | `search` (Atlas Search — **not** `vectorSearch`) |
| **Text field** | `text` (`ATLAS_SEARCH_INDEX_FIELD`), analyzed with the default `lucene.standard` analyzer |
| **Filter field** | `resource_id` (`ATLAS_SEARCH_INDEX_FILTER_FIELDS`), indexed as `token` (exact-match, not analyzed) — mirrors the vector index's `resource_id` filter field so hybrid retrieval pre-filters both queries identically |

**Atlas UI / `mongosh` index definition** (Atlas Search → Create Search Index → JSON Editor, or
`db.document_chunks.createSearchIndex("document_chunks_text_search", {...})` — `createSearchIndex`
defaults to `type: "search"` when unspecified, unlike the vector index which requires
`type: "vectorSearch"` explicitly):

```json
{
  "mappings": {
    "dynamic": false,
    "fields": {
      "text": { "type": "string" },
      "resource_id": { "type": "token" }
    }
  }
}
```

`dynamic: false` with an explicit field list mirrors the vector index's minimal, explicit
declaration — only `text` (searched) and `resource_id` (filtered) are ever queried by
`text_search()`; no other chunk field needs indexing.

**Setup steps:**
1. Use the same Atlas cluster as the vector index above.
2. Save, process, and embed at least one resource (same prerequisite as the vector index) so
   `document_chunks` actually has documents with `text` to search.
3. In the Atlas UI, open the target database → **Search** tab → **Create Search Index** → JSON
   Editor → paste the definition above → index it on the `document_chunks` collection → name it
   `document_chunks_text_search`.
4. Wait for the index to finish building, then `POST /api/v1/chat` uses it automatically —
   no code or config change needed once it's `READY`.

## `concepts`

A node in the personal knowledge graph. **Implemented in Phase 6** — written by
`app/services/graph_extraction_service.py` (via `app/db/concept_repository.py`), read by
`app/services/graph/builder.py` for `GET /api/v1/graph`. Not scoped by real auth yet — every
row currently gets the same placeholder `user_id` (`"single-tenant-user"`, matching
`app/services/rag/pipeline.py`'s constant of the same name/value, duplicated rather than
imported so Phase 6 has no dependency on any Phase 5 file) until Phase 8.

| field | type | notes |
|---|---|---|
| `_id` | ObjectId | exposed to clients as `id` (string) |
| `user_id` | string | |
| `name`, `normalized_name` | string | `normalized_name` is lowercased/whitespace-collapsed, the resolution/dedupe key (`app/db/concept_repository.py:find_by_normalized_name`) |
| `description` | string? | from the extracting LLM call, may be null |
| `aliases` | string[] | reserved for merged duplicate names; not populated yet -- resolution today keys on `normalized_name` only, never renames/aliases an existing concept |
| `source_resource_ids` | string[] | resources this concept was extracted from; grows via idempotent `$addToSet` as more resources mention it |
| `centrality_score` | float? | cached from the last `GET /api/v1/graph` call's centrality computation (`app/services/graph/traversal.py:compute_centrality`); `null` until the first graph read |
| `created_at`, `updated_at` | datetime | |

Model: `backend/app/models/concept.py`, camelCase on the wire (`sourceResourceIds`,
`centralityScore`, ...). Planned indexes: `(user_id, normalized_name)` -- not yet provisioned,
same deferred-to-Phase-8 status as every other collection's indexes (see `app/db/collections.py`).

## `edges`

A directed relationship between two concepts (`source` is a prerequisite/relation *of*
`target`). **Implemented in Phase 6** — same write/read path as `concepts` above, via
`app/db/edge_repository.py`.

| field | type | notes |
|---|---|---|
| `_id` | ObjectId | exposed to clients as `id` (string) |
| `user_id` | string | |
| `source_concept_id`, `target_concept_id` | string | FKs to `concepts._id` |
| `relation_type` | enum | `prerequisite_of` \| `related_to` \| `part_of` |
| `weight` | float | starts at `1.0`; each additional distinct evidence chunk for the same `(user_id, source_concept_id, target_concept_id, relation_type)` triple increments it by `1.0` (idempotent -- repeat evidence from the *same* chunk id is a no-op, not a re-increment) |
| `evidence_chunk_ids` | string[] | citation trail back to `document_chunks`, deduplicated via `$addToSet` |
| `created_at` | datetime | |

Model: `backend/app/models/edge.py`, camelCase on the wire. Planned indexes:
`(user_id, source_concept_id, target_concept_id)` -- not yet provisioned, same status as above.
No Atlas Search/Vector Search index is needed for either `concepts` or `edges` -- graph
construction and analysis both run in-process via NetworkX over a plain `find`, not an
aggregation pipeline.

## Access pattern

```
routes (app/api/v1/*) → services (app/services/*) → app/db/mongodb.get_database() → MongoDB Atlas
```

No route or service outside `app/db/` imports `motor` directly — `get_database()` is the only
way to reach a collection, which keeps persistence details swappable and testable in
isolation. Index provisioning (creating the standard indexes plus the two Atlas Search/Vector
Search indexes) is a deferred, one-time operational step — see [ROADMAP.md](./ROADMAP.md).
