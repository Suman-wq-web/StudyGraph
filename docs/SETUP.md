# Setup

First-time install and run instructions. For day-to-day conventions once you're up and
running, see [DEVELOPMENT.md](./DEVELOPMENT.md).

## Prerequisites

- Node.js 18.18+ (Next.js 14 requirement) and npm
- Python 3.11+
- A MongoDB instance — either a local `mongod` on the default port (`mongodb://localhost:27017`,
  the `.env.example` default) or a MongoDB Atlas cluster (free tier is enough). Required as of
  Phase 2: every `/api/v1/resources` endpoint reads/writes it, and so does the backend test
  suite (`backend/tests/conftest.py` points it at a separate `studygraph_test` database so
  tests never touch your dev data). A local `mongod` works for everything except **Atlas
  Vector Search** (Phase 4, implemented) — semantic search (`POST /api/v1/search/vector`)
  requires a real Atlas cluster with the `document_chunks_vector_index` provisioned; see
  [DATABASE.md](./DATABASE.md#atlas-vector-search-setup).
- A **Gemini** API key (`GEMINI_API_KEY`) — needed for embeddings (Phase 4, implemented) and
  semantic search. Get a free-tier key at https://aistudio.google.com/apikey. Document
  processing/chunking (Phase 3) uses `tiktoken` locally and needs no API key. Gemini, not
  OpenAI, is the embedding provider — see [ENVIRONMENT.md](./ENVIRONMENT.md) and
  [RAG.md](./RAG.md).

## 1. Clone and configure environment

```bash
git clone <repo-url> StudyGraph
cd StudyGraph
cp frontend/.env.local.example frontend/.env.local
cp backend/.env.example backend/.env
```

Edit both copied files with real values as you get them — see
[ENVIRONMENT.md](./ENVIRONMENT.md) for what each variable does. Placeholders work fine for
just running the current UI shell and health check.

## 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:3000` — it redirects to `/dashboard`.

## 3. Backend

```bash
cd backend
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -r requirements-dev.txt   # includes requirements.txt + pytest/httpx for tests
uvicorn main:app --reload
```

Visit `http://localhost:8000/health` — expect `{"status": "ok"}`. Interactive API docs are
auto-generated at `http://localhost:8000/docs`.

## 4. Verify

```bash
# Frontend production build
cd frontend && npm run build

# Backend tests
cd backend && pytest
```

Both should pass on a clean checkout with dependencies installed. If either fails, see
[DEVELOPMENT.md](./DEVELOPMENT.md) for troubleshooting conventions, or check
[ROADMAP.md](./ROADMAP.md) to confirm the feature you're expecting isn't simply not built yet.
